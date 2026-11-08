#include "4DPluginAPI.h"
#include "icu_runtime.hpp"
#include "split.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <initializer_list>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace {

using Clock = std::chrono::steady_clock;

struct Variable {
    PA_Variable value;
    bool owned = true;

    explicit Variable(PA_Variable input) : value(input) {}
    Variable(const Variable&) = delete;
    Variable& operator=(const Variable&) = delete;
    ~Variable()
    {
        if (owned) {
            PA_ClearVariable(&value);
        }
    }
};

struct String {
    PA_Unistring value{};
    explicit String(std::u16string_view text)
    {
        std::vector<PA_Unichar> buffer;
        buffer.reserve(text.size() + 1);
        for (auto unit : text) {
            buffer.push_back(static_cast<PA_Unichar>(unit));
        }
        buffer.push_back(0);
        value = PA_CreateUnistring(buffer.data());
        if (PA_GetLastError() != eER_NoErr) {
            throw splitter::Error("Host string allocation failed");
        }
    }
    String(const String&) = delete;
    String& operator=(const String&) = delete;
    ~String() { PA_DisposeUnistring(&value); }
};

void check_sdk()
{
    if (PA_GetLastError() != eER_NoErr) {
        throw splitter::Error("Host SDK operation failed");
    }
}

PA_Variable execute(PA_long32 command, PA_Variable* arguments, short count)
{
    PA_Variable result = PA_ExecuteCommandByID(command, arguments, count);
    check_sdk();
    return result;
}

std::u16string copy_text(PA_Unistring text, std::size_t ceiling = 16777216)
{
    static_assert(sizeof(PA_Unichar) == sizeof(char16_t));
    const auto length = PA_GetUnistringLength(&text);
    if (length < 0 || static_cast<std::size_t>(length) > ceiling) {
        throw splitter::Error("Text limit exceeded");
    }
    std::u16string result(static_cast<std::size_t>(length), u'\0');
    if (length != 0) {
        if (PA_GetUnistring(&text) == nullptr) {
            throw splitter::Error("Invalid host string");
        }
        std::memcpy(result.data(), PA_GetUnistring(&text), result.size() * sizeof(char16_t));
    }
    return result;
}

PA_Unistring string_value(PA_Variable value)
{
    auto text = PA_GetStringVariable(value);
    check_sdk();
    return text;
}

PA_Variable property(PA_ObjectRef object, std::u16string_view name)
{
    String key(name);
    PA_Variable result = PA_GetObjectProperty(object, &key.value);
    check_sdk();
    return result;
}

void allowed_keys(PA_ObjectRef object, std::initializer_list<std::u16string_view> allowed)
{
    PA_Variable arguments[2]{};
    PA_SetObjectVariable(&arguments[0], object);
    arguments[1] = PA_CreateVariable(eVK_ArrayUnicode);
    check_sdk();
    struct ArrayGuard {
        PA_Variable* value;
        ~ArrayGuard() { PA_ClearVariable(value); }
    } guard{&arguments[1]};
    PA_ExecuteCommandByID(1232, arguments, 2); // OB GET PROPERTY NAMES
    check_sdk();
    const auto count = PA_GetArrayNbElements(arguments[1]);
    check_sdk();
    if (count < 0 || static_cast<std::size_t>(count) > allowed.size()) {
        throw splitter::Error("Unknown options");
    }
    for (PA_long32 index = 1; index <= count; ++index) {
        auto text = PA_GetStringInArray(arguments[1], index);
        check_sdk();
        const auto key = copy_text(text, 64);
        if (std::find(allowed.begin(), allowed.end(), key) == allowed.end()) {
            throw splitter::Error("Unknown option");
        }
    }
}

bool absent(const PA_Variable& value)
{
    return PA_GetVariableKind(value) == eVK_Undefined;
}

std::size_t integer(const PA_Variable& value, std::size_t ceiling, bool allow_zero)
{
    double number;
    const auto kind = PA_GetVariableKind(value);
    if (kind == eVK_Longint) {
        number = PA_GetLongintVariable(value);
    } else if (kind == eVK_Real) {
        number = PA_GetRealVariable(value);
    } else {
        throw splitter::Error("Expected an integer");
    }
    if (!std::isfinite(number) || std::floor(number) != number ||
        number < (allow_zero ? 0 : 1) || number > static_cast<double>(ceiling)) {
        throw splitter::Error("Integer option outside supported range");
    }
    return static_cast<std::size_t>(number);
}

void size_option(PA_ObjectRef object, std::u16string_view name, std::size_t& setting)
{
    Variable value(property(object, name));
    if (!absent(value.value)) {
        setting = integer(value.value, setting, false);
    }
}

void int_option(PA_ObjectRef object, std::u16string_view name, std::int32_t& setting)
{
    Variable value(property(object, name));
    if (!absent(value.value)) {
        setting = static_cast<std::int32_t>(integer(value.value, setting, false));
    }
}

void boolean_option(PA_ObjectRef object, std::u16string_view name, bool& setting)
{
    Variable value(property(object, name));
    if (!absent(value.value)) {
        if (PA_GetVariableKind(value.value) != eVK_Boolean) {
            throw splitter::Error("Expected a Boolean flag");
        }
        setting = PA_GetBooleanVariable(value.value) != 0;
    }
}

enum class Mode { literal, literals, regex, graphemes };

struct Options {
    Mode mode = Mode::literal;
    splitter::Limits limits;
    splitter::RegexFlags regex_flags;
    std::vector<std::u16string> separators;
    std::optional<std::size_t> max_splits;
    bool regex_flags_present = false;
    bool separators_present = false;
};

Options parse_options(PA_ObjectRef object)
{
    Options result;
    if (object == nullptr) {
        return result;
    }
    allowed_keys(object, {u"mode", u"separators", u"maxSplits", u"regexFlags", u"limits"});
    Variable mode(property(object, u"mode"));
    bool explicit_mode = !absent(mode.value);
    if (explicit_mode) {
        if (PA_GetVariableKind(mode.value) != eVK_Unistring) {
            throw splitter::Error("Expected mode Text");
        }
        const auto name = copy_text(string_value(mode.value), 32);
        if (name == u"literal") result.mode = Mode::literal;
        else if (name == u"literals") result.mode = Mode::literals;
        else if (name == u"regex") result.mode = Mode::regex;
        else if (name == u"graphemes") result.mode = Mode::graphemes;
        else throw splitter::Error("Unknown mode");
    }
    Variable limits(property(object, u"limits"));
    if (!absent(limits.value)) {
        if (PA_GetVariableKind(limits.value) != eVK_Object ||
            PA_GetObjectVariable(limits.value) == nullptr) {
            throw splitter::Error("Expected limits Object");
        }
        const auto settings = PA_GetObjectVariable(limits.value);
        allowed_keys(settings, {u"maxInputUnits", u"maxPatternUnits", u"maxItems",
            u"maxOutputUnits", u"regexSteps", u"regexStackBytes", u"operationBudgetMs"});
        size_option(settings, u"maxInputUnits", result.limits.max_input_units);
        size_option(settings, u"maxPatternUnits", result.limits.max_pattern_units);
        size_option(settings, u"maxItems", result.limits.max_items);
        size_option(settings, u"maxOutputUnits", result.limits.max_output_units);
        int_option(settings, u"regexSteps", result.limits.regex_steps);
        int_option(settings, u"regexStackBytes", result.limits.regex_stack_bytes);
        int_option(settings, u"operationBudgetMs", result.limits.operation_budget_ms);
    }
    Variable maximum(property(object, u"maxSplits"));
    if (!absent(maximum.value)) {
        result.max_splits = integer(maximum.value, std::numeric_limits<std::int32_t>::max(), true);
    }
    Variable separators(property(object, u"separators"));
    if (!absent(separators.value)) {
        result.separators_present = true;
        if (PA_GetVariableKind(separators.value) != eVK_Collection) {
            throw splitter::Error("Expected separators Collection");
        }
        const auto collection = PA_GetCollectionVariable(separators.value);
        if (collection == nullptr) {
            throw splitter::Error("Null separators Collection");
        }
        const auto count = PA_GetCollectionLength(collection);
        check_sdk();
        if (count < 0 || count > 256) {
            throw splitter::Error("Separator count limit exceeded");
        }
        std::size_t units = 0;
        for (PA_long32 index = 0; index < count; ++index) {
            Variable value(PA_GetCollectionElement(collection, index));
            check_sdk();
            if (PA_GetVariableKind(value.value) != eVK_Unistring) {
                throw splitter::Error("Expected Text separator");
            }
            auto text = copy_text(string_value(value.value), 65536);
            if (text.empty() || text.size() > 65536 - units) {
                throw splitter::Error("Invalid separator list");
            }
            units += text.size();
            result.separators.push_back(std::move(text));
        }
        if (!explicit_mode) result.mode = Mode::literals;
    }
    Variable regex_flags(property(object, u"regexFlags"));
    if (!absent(regex_flags.value)) {
        result.regex_flags_present = true;
        if (PA_GetVariableKind(regex_flags.value) != eVK_Object ||
            PA_GetObjectVariable(regex_flags.value) == nullptr) {
            throw splitter::Error("Expected regexFlags Object");
        }
        const auto flags = PA_GetObjectVariable(regex_flags.value);
        allowed_keys(flags, {u"caseInsensitive", u"multiline", u"dotAll", u"comments",
                            u"unicodeWords", u"unixLines"});
        boolean_option(flags, u"caseInsensitive", result.regex_flags.case_insensitive);
        boolean_option(flags, u"multiline", result.regex_flags.multiline);
        boolean_option(flags, u"dotAll", result.regex_flags.dot_all);
        boolean_option(flags, u"comments", result.regex_flags.comments);
        boolean_option(flags, u"unicodeWords", result.regex_flags.unicode_words);
        boolean_option(flags, u"unixLines", result.regex_flags.unix_lines);
    }
    if ((result.separators_present != (result.mode == Mode::literals)) ||
        (result.regex_flags_present && result.mode != Mode::regex) ||
        (result.mode == Mode::graphemes && result.max_splits)) {
        throw splitter::Error("Options conflict with selected mode");
    }
    return result;
}

void module_anchor() {}

std::filesystem::path data_path()
{
#ifdef _WIN32
    HMODULE module = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            reinterpret_cast<LPCWSTR>(&module_anchor), &module)) {
        throw splitter::Error("Cannot locate plug-in module");
    }
    std::array<wchar_t, 32768> buffer{};
    const auto length = GetModuleFileNameW(module, buffer.data(), static_cast<DWORD>(buffer.size()));
    if (length == 0 || length >= buffer.size()) {
        throw splitter::Error("Cannot locate plug-in path");
    }
    std::filesystem::path path(std::wstring(buffer.data(), length));
#else
    Dl_info information{};
    if (dladdr(reinterpret_cast<const void*>(&module_anchor), &information) == 0 ||
        information.dli_fname == nullptr) {
        throw splitter::Error("Cannot locate plug-in path");
    }
    std::filesystem::path path(information.dli_fname);
#endif
    return path.parent_path().parent_path() / "Resources" / "icudt79l.dat";
}

void deadline(Clock::time_point start, const splitter::Limits& limits)
{
    if (Clock::now() - start > std::chrono::milliseconds(limits.operation_budget_ms)) {
        throw splitter::Error("Operation budget exceeded");
    }
}

void validate_output(PA_CollectionRef result, const splitter::Limits& limits,
                     Clock::time_point start)
{
    if (result == nullptr) throw splitter::Error("Host returned Null");
    const auto count = PA_GetCollectionLength(result);
    check_sdk();
    if (count < 0 || static_cast<std::size_t>(count) > limits.max_items) {
        throw splitter::Error("Output item limit exceeded");
    }
    std::size_t units = 0;
    for (PA_long32 index = 0; index < count; ++index) {
        deadline(start, limits);
        Variable value(PA_GetCollectionElement(result, index));
        check_sdk();
        if (PA_GetVariableKind(value.value) != eVK_Unistring) {
            throw splitter::Error("Host returned a non-Text field");
        }
        auto text = string_value(value.value);
        const auto length = PA_GetUnistringLength(&text);
        if (length < 0 || static_cast<std::size_t>(length) > limits.max_output_units - units) {
            throw splitter::Error("Output text limit exceeded");
        }
        units += static_cast<std::size_t>(length);
    }
}

std::u16string absent_delimiter(std::u16string_view source)
{
    constexpr char16_t first = 0xe000;
    constexpr std::size_t count = 0x1900;
    std::vector<std::uint32_t> frequencies(count);
    for (auto unit : source) {
        if (unit >= first && unit <= 0xf8ff) ++frequencies[unit - first];
    }
    const auto least = static_cast<std::size_t>(
        std::min_element(frequencies.begin(), frequencies.end()) - frequencies.begin());
    const auto prefix = static_cast<char16_t>(first + least);
    if (frequencies[least] == 0) return {prefix};
    std::vector<bool> follows(count);
    for (std::size_t index = 1; index < source.size(); ++index) {
        if (source[index - 1] == prefix && source[index] >= first && source[index] <= 0xf8ff) {
            follows[source[index] - first] = true;
        }
    }
    const auto missing = std::find(follows.begin(), follows.end(), false);
    if (missing == follows.end()) throw splitter::Error("Cannot isolate host trimming");
    return {prefix, static_cast<char16_t>(first + (missing - follows.begin()))};
}

void split(PA_PluginParameters params)
{
    const auto start = Clock::now();
    PA_Unistring* native_input = PA_GetStringParameter(params, 1);
    PA_Unistring* native_separator = PA_GetStringParameter(params, 2);
    if (!native_input || !native_separator) throw splitter::Error("Missing Text parameter");
    const auto flags = PA_GetLongParameter(params, 3);
    const auto options = parse_options(PA_GetObjectParameter(params, 4));
    const auto input = copy_text(*native_input, options.limits.max_input_units);
    const auto separator = copy_text(*native_separator, options.limits.max_input_units);
    deadline(start, options.limits);
    if (options.mode == Mode::literal && !options.max_splits) {
        // Bound native candidate allocation before delegating exact host semantics.
        splitter::literal(input, separator, std::nullopt, options.limits);
        PA_Variable arguments[3]{};
        PA_SetStringVariable(&arguments[0], native_input);
        PA_SetStringVariable(&arguments[1], native_separator);
        PA_SetLongintVariable(&arguments[2], flags);
        Variable result(execute(1554, arguments, 3));
        if (PA_GetVariableKind(result.value) != eVK_Collection) {
            throw splitter::Error("Invalid native split result");
        }
        const auto collection = PA_GetCollectionVariable(result.value);
        validate_output(collection, options.limits, start);
        PA_ReturnCollection(params, collection);
        result.owned = false;
        return;
    }
    if ((flags & ~3) != 0) throw splitter::Error("Unknown extended-mode native flags");
    if ((options.mode == Mode::literals || options.mode == Mode::graphemes) &&
        !separator.empty()) {
        throw splitter::Error("This mode requires an empty Text separator");
    }
    std::vector<splitter::Span> spans;
    switch (options.mode) {
    case Mode::literal:
        spans = splitter::literal(input, separator, options.max_splits, options.limits);
        break;
    case Mode::literals:
        spans = splitter::literals(input, options.separators, options.max_splits, options.limits);
        break;
    case Mode::regex:
        splitter::initialize_icu(data_path());
        spans = splitter::regex(input, separator, options.regex_flags,
                                options.max_splits, options.limits);
        break;
    case Mode::graphemes:
        splitter::initialize_icu(data_path());
        spans = splitter::graphemes(input, options.limits, (flags & 2) != 0);
        break;
    }
    Variable output(execute(1472, nullptr, 0));
    if (PA_GetVariableKind(output.value) != eVK_Collection) {
        throw splitter::Error("Invalid collection allocation");
    }
    const auto collection = PA_GetCollectionVariable(output.value);
    if (collection == nullptr) throw splitter::Error("Collection allocation failed");
    std::optional<String> trim_separator;
    if ((flags & 2) != 0 && options.mode != Mode::graphemes) {
        trim_separator.emplace(absent_delimiter(input));
    }
    PA_long32 output_index = 0;
    for (const auto& span : spans) {
        deadline(start, options.limits);
        if ((flags & 1) != 0 && span.length == 0) continue;
        PA_Variable arguments[3]{};
        PA_SetStringVariable(&arguments[0], native_input);
        PA_SetLongintVariable(&arguments[1], static_cast<PA_long32>(span.start + 1));
        PA_SetLongintVariable(&arguments[2], static_cast<PA_long32>(span.length));
        Variable text(execute(12, arguments, 3)); // Substring, native UTF-16 positions
        if (PA_GetVariableKind(text.value) != eVK_Unistring) {
            throw splitter::Error("Invalid host substring");
        }
        if (trim_separator) {
            PA_Variable trim[3]{};
            trim[0] = text.value;
            PA_SetStringVariable(&trim[1], &trim_separator->value);
            PA_SetLongintVariable(&trim[2], flags);
            Variable normalized(execute(1554, trim, 3));
            if (PA_GetVariableKind(normalized.value) != eVK_Collection) {
                throw splitter::Error("Invalid host trim result");
            }
            const auto fields = PA_GetCollectionVariable(normalized.value);
            if (fields == nullptr) throw splitter::Error("Null host trim result");
            const auto count = PA_GetCollectionLength(fields);
            check_sdk();
            if (count == 0) continue;
            if (count != 1) throw splitter::Error("Host trim delimiter was not isolated");
            Variable field(PA_GetCollectionElement(fields, 0));
            check_sdk();
            PA_SetCollectionElement(collection, output_index++, field.value);
        } else {
            PA_SetCollectionElement(collection, output_index++, text.value);
        }
        check_sdk();
    }
    validate_output(collection, options.limits, start);
    PA_ReturnCollection(params, collection);
    output.owned = false;
}

}

void PluginMain(PA_long32 selector, PA_PluginParameters params)
{
    if (selector != 1) return;
    try {
        split(params);
    } catch (const splitter::Error&) {
        PA_ReturnCollection(params, nullptr);
    } catch (const std::exception&) {
        std::fputs("Splitter: native operation failed.\n", stderr);
        PA_ReturnCollection(params, nullptr);
    } catch (...) {
        std::fputs("Splitter: unexpected native exception contained.\n", stderr);
        PA_ReturnCollection(params, nullptr);
    }
}
