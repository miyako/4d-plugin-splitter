#include "split.hpp"

#include <unicode/ubrk.h>
#include <unicode/uregex.h>
#include <unicode/utypes.h>

#include <algorithm>
#include <chrono>
#include <limits>
#include <memory>
#include <type_traits>
#include <utility>

namespace splitter {
namespace {

using Clock = std::chrono::steady_clock;

void require(bool condition, const char* message) {
    if (!condition) {
        throw Error(message);
    }
}

void check_icu(UErrorCode status, const char* operation) {
    if (U_FAILURE(status)) {
        throw Error(std::string(operation) + ": " + u_errorName(status));
    }
}

std::int32_t icu_length(std::size_t length) {
    require(length <= static_cast<std::size_t>(std::numeric_limits<std::int32_t>::max()),
            "UTF-16 length exceeds ICU index range");
    return static_cast<std::int32_t>(length);
}

void validate(const Limits& limits, std::u16string_view input) {
    const Limits hard;
    require(limits.max_input_units > 0 && limits.max_input_units <= hard.max_input_units,
            "invalid input limit");
    require(limits.max_pattern_units > 0 && limits.max_pattern_units <= hard.max_pattern_units,
            "invalid pattern limit");
    require(limits.max_items > 0 && limits.max_items <= hard.max_items,
            "invalid item limit");
    require(limits.max_output_units > 0 && limits.max_output_units <= hard.max_output_units,
            "invalid output limit");
    require(limits.regex_steps > 0 && limits.regex_steps <= hard.regex_steps,
            "invalid regex processing limit");
    require(limits.regex_stack_bytes > 0 &&
                limits.regex_stack_bytes <= hard.regex_stack_bytes,
            "invalid regex stack limit");
    require(limits.operation_budget_ms > 0 &&
                limits.operation_budget_ms <= hard.operation_budget_ms,
            "invalid operation budget");
    require(input.size() <= limits.max_input_units, "input limit exceeded");
    (void)icu_length(input.size());
}

void validate_pattern(std::size_t length, const Limits& limits) {
    require(length <= limits.max_pattern_units, "pattern limit exceeded");
    (void)icu_length(length);
}

class Operation {
public:
    explicit Operation(const Limits& limits)
        : limits_(limits),
          deadline_(Clock::now() + std::chrono::milliseconds(limits.operation_budget_ms)) {}

    bool expired() const noexcept { return Clock::now() >= deadline_; }

    void check() const {
        require(!expired(), "operation budget exceeded");
    }

    void tick() {
        if (++ticks_ == 1024) {
            ticks_ = 0;
            check();
        }
    }

    void candidate() {
        check();
        require(candidates_ < limits_.max_items, "match candidate limit exceeded");
        ++candidates_;
    }

    void emit(std::size_t start, std::size_t length) {
        check();
        require(spans.size() < limits_.max_items, "item limit exceeded");
        require(length <= limits_.max_output_units - output_units_, "output limit exceeded");
        output_units_ += length;
        spans.push_back({start, length});
    }

    std::vector<Span> spans;

private:
    const Limits& limits_;
    Clock::time_point deadline_;
    std::size_t ticks_ = 0;
    std::size_t candidates_ = 0;
    std::size_t output_units_ = 0;
};

// Conversion, rather than pointer punning, also works when ICU configures
// UChar as a distinct 16-bit integer type.
struct UnicodeBuffer {
    explicit UnicodeBuffer(std::u16string_view text) : units(std::max<std::size_t>(1, text.size())) {
        static_assert(sizeof(UChar) == sizeof(char16_t), "ICU must use 16-bit UChar");
        static_assert(std::is_integral<UChar>::value, "ICU UChar must be integral");
        std::transform(text.begin(), text.end(), units.begin(),
                       [](char16_t unit) { return static_cast<UChar>(unit); });
    }
    std::vector<UChar> units;
};

bool matches_at(std::u16string_view input, std::size_t position,
                std::u16string_view separator, Operation& operation) {
    if (separator.size() > input.size() - position) {
        return false;
    }
    for (std::size_t i = 0; i < separator.size(); ++i) {
        operation.tick();
        if (input[position + i] != separator[i]) {
            return false;
        }
    }
    return true;
}

template <typename Separators>
std::vector<Span> split_literals(std::u16string_view input,
                                 const Separators& separators,
                                 std::optional<std::size_t> max_splits,
                                 Operation& operation) {
    std::size_t cursor = 0;
    std::size_t position = 0;
    std::size_t consumed = 0;
    while (position < input.size() && (!max_splits || consumed < *max_splits)) {
        operation.tick();
        std::size_t longest = 0;
        for (const auto& separator : separators) {
            operation.tick();
            if (separator.size() > longest && matches_at(input, position, separator, operation)) {
                longest = separator.size();
            }
        }
        if (longest == 0) {
            ++position;
            continue;
        }
        operation.candidate();
        operation.emit(cursor, position - cursor);
        position += longest;
        cursor = position;
        ++consumed;
    }
    operation.emit(cursor, input.size() - cursor);
    return std::move(operation.spans);
}

UBool U_CALLCONV match_callback(const void* context, std::int32_t) {
    return !static_cast<const Operation*>(context)->expired();
}

UBool U_CALLCONV find_callback(const void* context, std::int64_t) {
    return !static_cast<const Operation*>(context)->expired();
}

} // namespace

std::vector<Span> literal(std::u16string_view input, std::u16string_view separator,
                          std::optional<std::size_t> max_splits, const Limits& limits) {
    validate(limits, input);
    validate_pattern(separator.size(), limits);
    Operation operation(limits);
    if (max_splits && *max_splits == 0) {
        operation.emit(0, input.size());
        return std::move(operation.spans);
    }
    if (separator.empty()) {
        std::size_t cursor = 0;
        std::size_t consumed = 0;
        while (cursor < input.size()) {
            if (max_splits && consumed == *max_splits) {
                operation.emit(cursor, input.size() - cursor);
                break;
            }
            operation.emit(cursor++, 1);
            ++consumed;
        }
        return std::move(operation.spans);
    }
    const std::u16string_view separators[] = {separator};
    return split_literals(input, separators, max_splits, operation);
}

std::vector<Span> literals(std::u16string_view input,
                           const std::vector<std::u16string>& separators,
                           std::optional<std::size_t> max_splits, const Limits& limits) {
    validate(limits, input);
    require(separators.size() <= 256, "separator count limit exceeded");
    std::size_t total = 0;
    for (const auto& separator : separators) {
        require(!separator.empty(), "empty list separator");
        require(separator.size() <= limits.max_pattern_units - total, "pattern limit exceeded");
        total += separator.size();
        (void)icu_length(separator.size());
    }
    Operation operation(limits);
    if (separators.empty()) {
        operation.emit(0, input.size());
        return std::move(operation.spans);
    }
    return split_literals(input, separators, max_splits, operation);
}

std::vector<Span> regex(std::u16string_view input, std::u16string_view pattern,
                        RegexFlags flags, std::optional<std::size_t> max_splits,
                        const Limits& limits) {
    validate(limits, input);
    validate_pattern(pattern.size(), limits);
    Operation operation(limits);
    UnicodeBuffer subject(input);
    UnicodeBuffer expression(pattern);
    operation.check();
    std::uint32_t options = 0;
    if (flags.case_insensitive) options |= UREGEX_CASE_INSENSITIVE;
    if (flags.multiline) options |= UREGEX_MULTILINE;
    if (flags.dot_all) options |= UREGEX_DOTALL;
    if (flags.comments) options |= UREGEX_COMMENTS;
    if (flags.unicode_words) options |= UREGEX_UWORD;
    if (flags.unix_lines) options |= UREGEX_UNIX_LINES;
    UErrorCode status = U_ZERO_ERROR;
    UParseError parse_error{};
    // ICU rejects an explicit zero length. Only the empty pattern uses its
    // owned single-NUL buffer with -1; nonempty patterns remain length-based.
    const std::int32_t pattern_length = pattern.empty() ? -1 : icu_length(pattern.size());
    std::unique_ptr<URegularExpression, decltype(&uregex_close)> matcher(
        uregex_open(expression.units.data(), pattern_length, options,
                    &parse_error, &status), &uregex_close);
    check_icu(status, "regex compilation");
    require(matcher != nullptr, "regex compilation returned no matcher");
    operation.check();
    uregex_setTimeLimit(matcher.get(), limits.regex_steps, &status);
    uregex_setStackLimit(matcher.get(), limits.regex_stack_bytes, &status);
    uregex_setMatchCallback(matcher.get(), match_callback, &operation, &status);
    uregex_setFindProgressCallback(matcher.get(), find_callback, &operation, &status);
    uregex_setText(matcher.get(), subject.units.data(), icu_length(input.size()), &status);
    check_icu(status, "regex configuration");
    std::size_t cursor = 0;
    std::size_t consumed = 0;
    while (!max_splits || consumed < *max_splits) {
        operation.check();
        const UBool found = uregex_findNext(matcher.get(), &status);
        operation.check();
        check_icu(status, "regex matching");
        if (!found) break;
        operation.candidate();
        const std::int32_t start = uregex_start(matcher.get(), 0, &status);
        const std::int32_t end = uregex_end(matcher.get(), 0, &status);
        check_icu(status, "regex boundaries");
        require(start >= 0 && end >= start &&
                    static_cast<std::size_t>(start) >= cursor &&
                    static_cast<std::size_t>(end) <= input.size(),
                "invalid regex boundaries");
        operation.emit(cursor, static_cast<std::size_t>(start) - cursor);
        cursor = static_cast<std::size_t>(end);
        ++consumed;
    }
    operation.emit(cursor, input.size() - cursor);
    return std::move(operation.spans);
}

std::vector<Span> graphemes(std::u16string_view input, const Limits& limits) {
    validate(limits, input);
    Operation operation(limits);
    if (input.empty()) return {};
    UnicodeBuffer subject(input);
    operation.check();
    UErrorCode status = U_ZERO_ERROR;
    std::unique_ptr<UBreakIterator, decltype(&ubrk_close)> iterator(
        ubrk_open(UBRK_CHARACTER, "root", subject.units.data(), icu_length(input.size()), &status),
        &ubrk_close);
    check_icu(status, "grapheme iterator");
    require(iterator != nullptr, "grapheme iterator returned no iterator");
    std::int32_t start = ubrk_first(iterator.get());
    require(start == 0, "invalid initial grapheme boundary");
    for (;;) {
        operation.check();
        const std::int32_t end = ubrk_next(iterator.get());
        if (end == UBRK_DONE) break;
        require(end > start && static_cast<std::size_t>(end) <= input.size(),
                "invalid grapheme boundary");
        operation.candidate();
        operation.emit(static_cast<std::size_t>(start), static_cast<std::size_t>(end - start));
        start = end;
    }
    require(static_cast<std::size_t>(start) == input.size(), "incomplete grapheme boundaries");
    return std::move(operation.spans);
}

} // namespace splitter
