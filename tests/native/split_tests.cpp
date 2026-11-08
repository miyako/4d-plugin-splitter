#include "split.hpp"
#include "icu_runtime.hpp"

#include <atomic>
#include <exception>
#include <filesystem>
#include <functional>
#include <iostream>
#include <limits>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

using splitter::Limits;
using splitter::RegexFlags;
using splitter::Span;
const std::optional<std::size_t> unlimited = std::nullopt;
const Limits defaults;
std::atomic<std::size_t> checks{0};

void check(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}

void fields(std::u16string_view source, const std::vector<Span>& spans,
            const std::vector<std::u16string>& expected) {
    check(spans.size() == expected.size(), "unexpected field count");
    std::size_t previous_end = 0;
    std::u16string reconstructed;
    for (std::size_t i = 0; i < spans.size(); ++i) {
        const auto span = spans[i];
        check(span.start >= previous_end && span.start <= source.size(),
              "unordered or invalid original offset");
        check(span.length <= source.size() - span.start, "invalid original span length");
        const auto raw = source.substr(span.start, span.length);
        check(raw == expected[i], "unexpected original field contents");
        reconstructed.append(source.substr(previous_end, span.start - previous_end));
        reconstructed.append(raw);
        previous_end = span.start + span.length;
    }
    reconstructed.append(source.substr(previous_end));
    check(reconstructed == source, "original UTF-16 cannot be reconstructed");
}

template <typename Function>
void error(Function&& action, const char* contains = nullptr) {
    try {
        action();
    } catch (const splitter::Error& failure) {
        check(!std::string(failure.what()).empty(), "Error must carry a message");
        if (contains) {
            if (std::string(failure.what()).find(contains) == std::string::npos) {
                throw std::runtime_error(std::string("expected failure containing ") +
                                         contains + "; received: " + failure.what());
            }
            ++checks;
        }
        return;
    }
    throw std::runtime_error("expected splitter::Error");
}

void literal_tests() {
    fields(u"a,,b,", splitter::literal(u"a,,b,", u",", unlimited, defaults),
           {u"a", u"", u"b", u""});
    fields(u"", splitter::literal(u"", u",", unlimited, defaults), {u""});
    fields(u"", splitter::literal(u"", u"", unlimited, defaults), {});
    fields(u"", splitter::literal(u"", u"", 0, defaults), {u""});
    fields(u"abc", splitter::literal(u"abc", u"", unlimited, defaults), {u"a", u"b", u"c"});
    fields(u"abc", splitter::literal(u"abc", u"", 1, defaults), {u"a", u"bc"});
    fields(u"abc", splitter::literal(u"abc", u"", 2, defaults), {u"a", u"b", u"c"});
    fields(u"abc", splitter::literal(u"abc", u"", 3, defaults), {u"a", u"b", u"c"});
    fields(u"abc", splitter::literal(u"abc", u"", 0, defaults), {u"abc"});
    fields(u"a,b,c,", splitter::literal(u"a,b,c,", u",", 1, defaults), {u"a", u"b,c,"});
    fields(u"a,b,c,", splitter::literal(u"a,b,c,", u",", 0, defaults), {u"a,b,c,"});
    fields(u"aaaaa", splitter::literal(u"aaaaa", u"aa", unlimited, defaults), {u"", u"", u"a"});
    fields(u"ab", splitter::literal(u"ab", u"long", unlimited, defaults), {u"ab"});
    fields(u" a , b ", splitter::literal(u" a , b ", u",", unlimited, defaults),
           {u" a ", u" b "});
    fields(u"e\u0301,é", splitter::literal(u"e\u0301,é", u"é", unlimited, defaults),
           {u"e\u0301,", u""});
    const std::u16string nul_source{u'a', 0, u'b', 0, u'c'};
    const std::u16string nul_separator(1, 0);
    fields(nul_source, splitter::literal(nul_source, nul_separator, unlimited, defaults),
           {u"a", u"b", u"c"});
    const std::u16string malformed{0xd800, u'x', 0xdc00};
    fields(malformed, splitter::literal(malformed, u"x", unlimited, defaults),
           {std::u16string(1, 0xd800), std::u16string(1, 0xdc00)});
    const std::u16string emoji = u"😀";
    fields(emoji, splitter::literal(emoji, u"", unlimited, defaults),
           {emoji.substr(0, 1), emoji.substr(1)});
    const auto offsets = splitter::literal(u"x::y", u"::", unlimited, defaults);
    check(offsets[0].start == 0 && offsets[0].length == 1 &&
              offsets[1].start == 3 && offsets[1].length == 1,
          "literal offsets are not original UTF-16 offsets");
    fields(u"a,b", splitter::literal(u"a,b", u",", std::numeric_limits<std::size_t>::max(),
                                    defaults), {u"a", u"b"});
}

void list_tests() {
    fields(u"a::b:c", splitter::literals(u"a::b:c", {u":", u"::"}, unlimited, defaults),
           {u"a", u"b", u"c"});
    fields(u"a::b:c", splitter::literals(u"a::b:c", {u"::", u":"}, unlimited, defaults),
           {u"a", u"b", u"c"});
    fields(u"x--y,z", splitter::literals(u"x--y,z", {u",", u"--"}, 1, defaults),
           {u"x", u"y,z"});
    fields(u"ababa", splitter::literals(u"ababa", {u"ba", u"ab"}, unlimited, defaults),
           {u"", u"", u"a"});
    fields(u"a,b", splitter::literals(u"a,b", {u",", u","}, unlimited, defaults),
           {u"a", u"b"});
    fields(u"a,b", splitter::literals(u"a,b", {}, unlimited, defaults), {u"a,b"});
    fields(u"", splitter::literals(u"", {}, unlimited, defaults), {u""});
    fields(u"", splitter::literals(u"", {u","}, unlimited, defaults), {u""});
    fields(u"a,b", splitter::literals(u"a,b", {u","}, 0, defaults), {u"a,b"});
    error([] { splitter::literals(u"x", {u"", u","}, unlimited, defaults); }, "empty");
    error([] { splitter::literals(u"x", {u""}, 0, defaults); }, "empty");
    const std::vector<std::u16string> largest_list(256, u",");
    fields(u"a,b", splitter::literals(u"a,b", largest_list, unlimited, defaults),
           {u"a", u"b"});
    error([] {
        splitter::literals(u"", std::vector<std::u16string>(257, u","), unlimited, defaults);
    }, "count");
    error([] {
        splitter::literals(u"", {std::u16string(32769, u'a'), std::u16string(32768, u'b')},
                           unlimited, defaults);
    }, "pattern");
    const std::u16string nul_source{u'a', 0, u'b', u';', u'c'};
    fields(nul_source, splitter::literals(nul_source, {std::u16string(1, 0), u";"},
                                         unlimited, defaults), {u"a", u"b", u"c"});
}

void regex_tests() {
    fields(u"a,,b,", splitter::regex(u"a,,b,", u",", {}, unlimited, defaults),
           {u"a", u"", u"b", u""});
    fields(u"a,b,c,", splitter::regex(u"a,b,c,", u",", {}, 1, defaults), {u"a", u"b,c,"});
    fields(u"a,b", splitter::regex(u"a,b", u",", {}, 0, defaults), {u"a,b"});
    fields(u"", splitter::regex(u"", u",", {}, unlimited, defaults), {u""});
    fields(u"", splitter::regex(u"", u"", {}, unlimited, defaults), {u"", u""});
    fields(u"", splitter::regex(u"", u"^|$", {}, unlimited, defaults), {u"", u""});
    fields(u"", splitter::regex(u"", u"", {}, 0, defaults), {u""});
    fields(u"", splitter::regex(u"", u"", {}, 1, defaults), {u"", u""});
    fields(u"ab", splitter::regex(u"ab", u"", {}, unlimited, defaults), {u"", u"a", u"b", u""});
    fields(u"ab", splitter::regex(u"ab", u"", {}, 1, defaults), {u"", u"ab"});
    fields(u"ab", splitter::regex(u"ab", u"", {}, 2, defaults), {u"", u"a", u"b"});
    fields(u"ab", splitter::regex(u"ab", u"(?=b)", {}, unlimited, defaults), {u"a", u"b"});
    fields(u"ab", splitter::regex(u"ab", u"^|$", {}, unlimited, defaults), {u"", u"ab", u""});
    fields(u"a,b;c", splitter::regex(u"a,b;c", u"([,;])", {}, unlimited, defaults),
           {u"a", u"b", u"c"});
    fields(u"😀x", splitter::regex(u"😀x", u"", {}, unlimited, defaults),
           {u"", u"😀", u"x", u""});
    const auto offsets = splitter::regex(u"😀x", u"", {}, unlimited, defaults);
    check(offsets[1].start == 0 && offsets[1].length == 2 &&
              offsets[2].start == 2 && offsets[3].start == 3,
          "zero-width advancement split a surrogate pair");
    fields(u"xéyÉz", splitter::regex(u"xéyÉz", u"É", {}, unlimited, defaults), {u"xéy", u"z"});
    RegexFlags flags;
    flags.case_insensitive = true;
    fields(u"xéyÉz", splitter::regex(u"xéyÉz", u"É", flags, unlimited, defaults),
           {u"x", u"y", u"z"});
    flags = {};
    fields(u"a\nb", splitter::regex(u"a\nb", u"^", flags, unlimited, defaults), {u"", u"a\nb"});
    flags.multiline = true;
    fields(u"a\nb", splitter::regex(u"a\nb", u"^", flags, unlimited, defaults),
           {u"", u"a\n", u"b"});
    flags = {};
    fields(u"a\nb", splitter::regex(u"a\nb", u".", flags, unlimited, defaults),
           {u"", u"\n", u""});
    flags.dot_all = true;
    fields(u"a\nb", splitter::regex(u"a\nb", u".", flags, unlimited, defaults),
           {u"", u"", u"", u""});
    flags = {};
    flags.comments = true;
    fields(u"a,b", splitter::regex(u"a,b", u" , # delimiter", flags, unlimited, defaults),
           {u"a", u"b"});
    fields(u"a,b", splitter::regex(u"a,b", u" , # delimiter", {}, unlimited, defaults),
           {u"a,b"});
    flags = {};
    fields(u"can't", splitter::regex(u"can't", u"\\b", flags, unlimited, defaults),
           {u"", u"can", u"'", u"t", u""});
    flags.unicode_words = true;
    fields(u"can't", splitter::regex(u"can't", u"\\b", flags, unlimited, defaults),
           {u"", u"can't", u""});
    flags = {};
    fields(u"a\u0085b", splitter::regex(u"a\u0085b", u".", flags, unlimited, defaults),
           {u"", u"\u0085", u""});
    flags.unix_lines = true;
    fields(u"a\u0085b", splitter::regex(u"a\u0085b", u".", flags, unlimited, defaults),
           {u"", u"", u"", u""});
    const std::u16string nul_source{u'a', 0, u'b'};
    fields(nul_source, splitter::regex(nul_source, std::u16string(1, 0), {},
                                      unlimited, defaults), {u"a", u"b"});
    const std::u16string nul_pattern{0, u'b'};
    fields(nul_source, splitter::regex(nul_source, nul_pattern, {}, unlimited, defaults),
           {u"a", u""});
    fields(nul_source, splitter::regex(nul_source, u"", {}, unlimited, defaults),
           {u"", u"a", std::u16string(1, 0), u"b", u""});
    const std::u16string malformed{0xd800, u'x', 0xdc00};
    fields(malformed, splitter::regex(malformed, u"x", {}, unlimited, defaults),
           {std::u16string(1, 0xd800), std::u16string(1, 0xdc00)});
    fields(u"e\u0301é", splitter::regex(u"e\u0301é", u"é", {}, unlimited, defaults),
           {u"e\u0301", u""});
    error([] { splitter::regex(u"abc", u"(", {}, unlimited, defaults); }, "compilation");
    error([] { splitter::regex(u"abc", u"(", {}, 0, defaults); }, "compilation");
}

void grapheme_regex_tests() {
    RegexFlags flags;
    flags.grapheme_dots = true;
    const auto split = [&](std::u16string_view source, std::u16string_view pattern,
                           const std::vector<std::u16string>& expected) {
        try {
            fields(source, splitter::regex(source, pattern, flags, unlimited, defaults), expected);
        } catch (const std::exception& failure) {
            throw std::runtime_error(std::string(pattern.begin(), pattern.end()) + ": " +
                                     failure.what());
        }
    };
    split(u"e\u0301👩‍💻👍🏽🇯🇵", u".", {u"", u"", u"", u"", u""});
    split(u"e\u0301👩‍💻x", u".{2}", {u"", u"x"});
    split(u"e\u0301👩‍💻x", u"(.)(.)", {u"", u"x"});
    split(u"e\u0301e\u0301x", u"(.)\\1", {u"", u"x"});
    split(u"e\u0301\n👩‍💻\r\n👍🏽\u0085🇯🇵\u2028x\u2029", u".",
          {u"", u"\n", u"\r\n", u"\u0085", u"\u2028", u"\u2029"});
    split(u"e\u0301\r\nx", u"\\X", {u"", u"", u"", u""});
    split(u"a.e\u0301", u"\\.", {u"a", u"e\u0301"});
    split(u"a.e\u0301", u"[.]", {u"a", u"e\u0301"});
    split(u"a.e\u0301", u"[[.][,]]", {u"a", u"e\u0301"});
    split(u"a.e\u0301", u"[[:punct:]]", {u"a", u"e\u0301"});
    split(u"a.e\u0301", u"[]a.]", {u"", u"", u"e\u0301"});
    split(u"a.e\u0301", u"[\\]]|\\.", {u"a", u"e\u0301"});
    split(u"ae\u0301", u"[^^].", {u"", u""});
    split(u"a.e\u0301", u"\\Q.\\E", {u"a", u"e\u0301"});
    split(u"a.e\u0301", u"(?# . ( )\\.", {u"a", u"e\u0301"});
    split(u"e\u0301", u"(?x) # . [ ( \\Q \n .", {u"", u""});
    split(u"e\u0301", u"(?x: # . [ ( \\Q \n .)", {u"", u""});
    split(u"e\u0301", u"(?x)# .\u0085.", {u"", u""});
    split(u"e\u0301", u"(?x)# .\u2028.", {u"", u""});
    split(u"e\u0301#👩‍💻", u"(?x:(?-x:.#))", {u"", u"👩‍💻"});
    split(u"e\u0301#👩‍💻", u"(?x:.)(?-x)#.", {u"", u""});
    split(u"e\u0301#👩‍💻", u"(?x)(?-x # . [ (\n:.#.)", {u"", u""});
    split(u"e\u0301\nx", u"(?s:.)", {u"", u"", u"", u""});
    split(u"e\u0301\nx", u"(?s)(?-s:.)", {u"", u"\n", u""});
    split(u"\r\nx", u"(?d:.)", {u"\r\n", u""});
    split(u"\r\nx", u"(?ds:.)", {u"", u"", u""});
    split(u"\u0085x", u"(?d:.)", {u"", u"", u""});
    split(u"", u"", {u"", u""});
    split(u"e\u0301", u"", {u"", u"e", u"\u0301", u""});
    fields(u"e\u0301👩‍💻x", splitter::regex(u"e\u0301👩‍💻x", u".", flags, 1, defaults),
           {u"", u"👩‍💻x"});
    flags.comments = true;
    split(u"e\u0301", u" # . [ ( \\Q \n .", {u"", u""});
    split(u"e\u0301", u"(?-x:.)", {u"", u""});
    split(u"e\u0301", u"( ? x : . )", {u"", u""});
    split(u"e\u0301#👩‍💻", u"( ? - x :.#.)", {u"", u""});
    split(u"a.e\u0301", u"( ? # . [ ( )\\.", {u"a", u"e\u0301"});
    split(u"a.e\u0301", u"\\Q.\\E", {u"a", u"e\u0301"});
    flags.comments = false;
    flags.dot_all = true;
    split(u"\r\nx", u".", {u"", u"", u""});
    flags.dot_all = false;
    flags.unix_lines = true;
    split(u"\r\nx", u".", {u"\r\n", u""});
    split(u"\rx", u".", {u"", u"", u""});
    flags.unix_lines = false;
    Limits limits;
    limits.max_pattern_units = 1;
    fields(u"e\u0301", splitter::regex(u"e\u0301", u".", flags, unlimited, limits),
           {u"", u""});
    error([&] { splitter::regex(u"abc", u"(.(", flags, unlimited, defaults); }, "compilation");
    error([&] { splitter::regex(u"abc", u"..", flags, unlimited, limits); }, "pattern");
}

void grapheme_tests() {
    fields(u"", splitter::graphemes(u"", defaults), {});
    fields(u"\r\nx", splitter::graphemes(u"\r\nx", defaults), {u"\r\n", u"x"});
    fields(u"e\u0301é", splitter::graphemes(u"e\u0301é", defaults), {u"e\u0301", u"é"});
    fields(u"👩‍💻👍🏽🇯🇵🇺🇸", splitter::graphemes(u"👩‍💻👍🏽🇯🇵🇺🇸", defaults),
           {u"👩‍💻", u"👍🏽", u"🇯🇵", u"🇺🇸"});
    fields(u"日あ한ا\u0654", splitter::graphemes(u"日あ한ا\u0654", defaults),
           {u"日", u"あ", u"한", u"ا\u0654"});
    fields(u"\u1100\u1161\u11a8", splitter::graphemes(u"\u1100\u1161\u11a8", defaults),
           {u"\u1100\u1161\u11a8"});
    const std::u16string nul_source{u'a', 0, u'b'};
    fields(nul_source, splitter::graphemes(nul_source, defaults),
           {u"a", std::u16string(1, 0), u"b"});
    const std::u16string malformed{0xd800, u'x', 0xdc00};
    fields(malformed, splitter::graphemes(malformed, defaults),
           {std::u16string(1, 0xd800), u"x", std::u16string(1, 0xdc00)});
    const auto spans = splitter::graphemes(u"😀é", defaults);
    check(spans[0].start == 0 && spans[0].length == 2 &&
              spans[1].start == 2 && spans[1].length == 1,
          "grapheme offsets are not UTF-16 offsets");
    const std::u16string whitespace =
        u"\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004"
        u"\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000";
    for (const auto unit : whitespace) {
        const std::u16string source(1, unit);
        fields(source, splitter::graphemes(source, defaults), {source});
        fields(source, splitter::graphemes(source, defaults, true), {u""});
        fields(source, splitter::regex(source, u"\\s", {}, unlimited, defaults), {u"", u""});
    }
    fields(u"\r\nx", splitter::graphemes(u"\r\nx", defaults, true), {u"", u"x"});
    fields(u" \u0301😀\u00a0", splitter::graphemes(u" \u0301😀\u00a0", defaults, true),
           {u"\u0301", u"😀", u""});
    fields(malformed, splitter::graphemes(malformed, defaults, true),
           {std::u16string(1, 0xd800), u"x", std::u16string(1, 0xdc00)});
    for (const auto unit : std::u16string{u'\0', u'\u001c', u'\u180e', u'\u200b',
                                        u'\u200d', u'\u2060', u'\ufeff'}) {
        const std::u16string source(1, unit);
        fields(source, splitter::graphemes(source, defaults, true), {source});
        fields(source, splitter::regex(source, u"\\s", {}, unlimited, defaults), {source});
    }
    fields(u"", splitter::graphemes(u"", defaults, true), {});
    Limits limits;
    limits.max_items = 1;
    error([&] { splitter::graphemes(u"\t ", limits, true); }, "limit");
    limits = defaults;
    limits.max_output_units = 1;
    error([&] { splitter::graphemes(u"\r\n", limits, true); }, "output");
}

void limit_tests() {
    Limits limits;
    limits.max_input_units = 2;
    error([&] { splitter::literal(u"abc", u",", unlimited, limits); }, "input");
    error([&] { splitter::literals(u"abc", {}, unlimited, limits); }, "input");
    error([&] { splitter::regex(u"abc", u",", {}, unlimited, limits); }, "input");
    error([&] { splitter::graphemes(u"abc", limits); }, "input");
    fields(u"ab", splitter::literal(u"ab", u",", unlimited, limits), {u"ab"});
    limits = {};
    limits.max_pattern_units = 2;
    error([&] { splitter::literal(u"", u"abc", unlimited, limits); }, "pattern");
    error([&] { splitter::literals(u"", {u"ab", u"c"}, unlimited, limits); }, "pattern");
    error([&] { splitter::regex(u"", u"abc", {}, unlimited, limits); }, "pattern");
    limits = {};
    limits.max_items = 2;
    error([&] { splitter::literal(u"a,b,c", u",", unlimited, limits); }, "item");
    error([&] { splitter::literal(u"abc", u"", unlimited, limits); }, "item");
    error([&] { splitter::literals(u"a,b,c", {u","}, unlimited, limits); }, "item");
    error([&] { splitter::regex(u"ab", u"", {}, unlimited, limits); });
    error([&] { splitter::graphemes(u"abc", limits); });
    fields(u"a,b,c", splitter::literal(u"a,b,c", u",", 1, limits), {u"a", u"b,c"});
    fields(u"ab", splitter::regex(u"ab", u"", {}, 1, limits), {u"", u"ab"});
    limits = {};
    limits.max_output_units = 3;
    error([&] { splitter::literal(u"ab,cd", u",", unlimited, limits); }, "output");
    error([&] { splitter::literals(u"ab,cd", {u","}, unlimited, limits); }, "output");
    error([&] { splitter::regex(u"ab,cd", u",", {}, unlimited, limits); }, "output");
    error([&] { splitter::graphemes(u"abcd", limits); }, "output");
    error([&] { splitter::literal(u"ab,cd", u",", 0, limits); }, "output");
    limits.max_output_units = 4;
    fields(u"ab,cd", splitter::literal(u"ab,cd", u",", unlimited, limits), {u"ab", u"cd"});
    limits.max_output_units = 1;
    fields(u",,,", splitter::regex(u",,,", u",", {}, unlimited, limits), {u"", u"", u"", u""});

    const std::vector<std::function<void(Limits&)>> invalid_limits = {
        [](Limits& l) { l.max_input_units = 0; },
        [](Limits& l) { ++l.max_input_units; },
        [](Limits& l) { l.max_pattern_units = 0; },
        [](Limits& l) { ++l.max_pattern_units; },
        [](Limits& l) { l.max_items = 0; },
        [](Limits& l) { ++l.max_items; },
        [](Limits& l) { l.max_output_units = 0; },
        [](Limits& l) { ++l.max_output_units; },
        [](Limits& l) { l.regex_steps = 0; },
        [](Limits& l) { l.regex_steps = -1; },
        [](Limits& l) { ++l.regex_steps; },
        [](Limits& l) { l.regex_stack_bytes = 0; },
        [](Limits& l) { l.regex_stack_bytes = -1; },
        [](Limits& l) { ++l.regex_stack_bytes; },
        [](Limits& l) { l.operation_budget_ms = 0; },
        [](Limits& l) { l.operation_budget_ms = -1; },
        [](Limits& l) { ++l.operation_budget_ms; }
    };
    for (const auto& invalidate : invalid_limits) {
        limits = {};
        invalidate(limits);
        error([&] { splitter::literal(u"", u"", unlimited, limits); }, "invalid");
        error([&] { splitter::literals(u"", {}, unlimited, limits); }, "invalid");
        error([&] { splitter::regex(u"", u"", {}, unlimited, limits); }, "invalid");
        error([&] { splitter::graphemes(u"", limits); }, "invalid");
    }

    limits = {};
    limits.regex_steps = 1;
    const std::u16string adversarial = std::u16string(4096, u'a') + u"!";
    error([&] { splitter::regex(adversarial, u"(a+)+$", {}, unlimited, limits); },
          "U_REGEX_TIME_OUT");
    limits = {};
    limits.regex_stack_bytes = 256;
    error([&] { splitter::regex(adversarial, u"(a+)+$", {}, unlimited, limits); },
          "U_REGEX_STACK_OVERFLOW");
    limits = {};
    limits.operation_budget_ms = 1;
    const std::u16string long_input(1048576, u'a');
    const std::u16string long_separator = std::u16string(1024, u'a') + u"b";
    error([&] { splitter::literal(long_input, long_separator, unlimited, limits); }, "budget");
    error([&] { splitter::literals(long_input, {long_separator}, unlimited, limits); }, "budget");
    error([&] { splitter::regex(adversarial, u"(a+)+$", {}, unlimited, limits); }, "budget");

    // Many cheap matches must share one deadline, not receive a fresh budget.
    limits.max_items = 100000;
    const std::u16string many_matches(99998, u'a');
    error([&] { splitter::regex(many_matches, u"a", {}, unlimited, limits); }, "budget");
    error([&] { splitter::graphemes(many_matches, limits); }, "budget");
    fields(u"a,b", splitter::regex(u"a,b", u",", {}, unlimited, defaults), {u"a", u"b"});

    // Unit ceilings are UTF-16 units, not bytes or Unicode scalar values.
    limits = {};
    limits.max_input_units = 1;
    error([&] { splitter::graphemes(u"😀", limits); }, "input");
    limits.max_input_units = 2;
    fields(u"😀", splitter::graphemes(u"😀", limits), {u"😀"});
    limits.max_output_units = 1;
    error([&] { splitter::graphemes(u"😀", limits); }, "output");
    limits.max_output_units = 2;
    fields(u"😀", splitter::graphemes(u"😀", limits), {u"😀"});
    limits = {};
    limits.max_pattern_units = 1;
    error([&] { splitter::regex(u"x😀y", u"😀", {}, unlimited, limits); }, "pattern");
    limits.max_pattern_units = 2;
    fields(u"x😀y", splitter::regex(u"x😀y", u"😀", {}, unlimited, limits), {u"x", u"y"});
    limits.max_pattern_units = 1;
    fields(u"a", splitter::regex(u"a", u"", {}, unlimited, limits), {u"", u"a", u""});
}

void thread_tests() {
    constexpr std::size_t workers = 8;
    std::atomic<bool> start{false};
    std::vector<std::exception_ptr> failures(workers);
    std::vector<std::thread> threads;
    threads.reserve(workers);
    try {
        for (std::size_t worker = 0; worker < workers; ++worker) {
            threads.emplace_back([&, worker] {
                while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
                try {
                    const std::u16string id(1, static_cast<char16_t>(u'a' + worker));
                    const std::u16string source = id + u",😀;e\u0301|👩‍💻";
                    const std::u16string clusters = u"e\u0301👩‍💻👍🏽🇯🇵\r\n" + id;
                    const std::u16string zero_width = u"😀" + id;
                    for (std::size_t iteration = 0; iteration < 64; ++iteration) {
                        fields(source, splitter::regex(source, u"[,;|]", {}, unlimited, defaults),
                               {id, u"😀", u"e\u0301", u"👩‍💻"});
                        fields(clusters, splitter::graphemes(clusters, defaults),
                               {u"e\u0301", u"👩‍💻", u"👍🏽", u"🇯🇵", u"\r\n", id});
                        RegexFlags flags;
                        flags.grapheme_dots = true;
                        fields(clusters, splitter::regex(clusters, u".", flags,
                                                         unlimited, defaults),
                               {u"", u"", u"", u"", u"\r\n", u""});
                        fields(zero_width, splitter::regex(zero_width, u"", {},
                                                           unlimited, defaults),
                               {u"", u"😀", id, u""});
                        fields(source, splitter::literals(source, {u",", u";", u"|"},
                                                          2, defaults),
                               {id, u"😀", u"e\u0301|👩‍💻"});
                        if (iteration % 16 == 0) {
                            error([] { splitter::regex(u"x", u"(", {}, unlimited, defaults); },
                                  "compilation");
                        }
                    }
                } catch (...) {
                    failures[worker] = std::current_exception();
                }
            });
        }
    } catch (...) {
        start.store(true, std::memory_order_release);
        for (auto& thread : threads) thread.join();
        throw;
    }
    start.store(true, std::memory_order_release);
    for (auto& thread : threads) thread.join();
    for (const auto& failure : failures) {
        if (failure) std::rethrow_exception(failure);
    }
    check(true, "independent native calls completed");
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: split_tests <private-ICU-data-file>\n";
        return 2;
    }
    try {
        splitter::initialize_icu(std::filesystem::path(argv[1]));
        literal_tests();
        list_tests();
        regex_tests();
        grapheme_regex_tests();
        grapheme_tests();
        limit_tests();
        thread_tests();
        std::cout << "split_tests: " << checks.load() << " checks passed\n";
        return 0;
    } catch (const std::exception& failure) {
        std::cerr << "split_tests: " << failure.what() << '\n';
        return 1;
    }
}
