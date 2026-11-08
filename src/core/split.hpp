#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace splitter {

struct Span {
    std::size_t start;
    std::size_t length;
};

// Defaults are also hard ceilings; callers may only lower them.
struct Limits {
    std::size_t max_input_units = 16777216;
    std::size_t max_pattern_units = 65536;
    std::size_t max_items = 100000;
    std::size_t max_output_units = 33554432;
    // ICU processing-time units (uregex_setTimeLimit), not a wall-clock timeout.
    std::int32_t regex_steps = 1000;
    std::int32_t regex_stack_bytes = 8388608;
    std::int32_t operation_budget_ms = 5000;
};

struct RegexFlags {
    bool case_insensitive = false;
    bool multiline = false;
    bool dot_all = false;
    bool comments = false;
    bool unicode_words = false;
    bool unix_lines = false;
};

class Error : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// All offsets address the original UTF-16 input. No normalization, trimming,
// filtering, delimiter retention, or capture expansion is performed.
// max_splits == 0 returns one unsplit field, including for empty input.
// An empty literal separator splits code units; empty input then has no fields.
std::vector<Span> literal(std::u16string_view input,
                          std::u16string_view separator,
                          std::optional<std::size_t> max_splits,
                          const Limits& limits);
// At most 256 nonempty separators, with at most max_pattern_units combined
// UTF-16 units. Earliest match wins, then longest match, then list order.
std::vector<Span> literals(std::u16string_view input,
                           const std::vector<std::u16string>& separators,
                           std::optional<std::size_t> max_splits,
                           const Limits& limits);
// ICU zero-width boundaries, including start/end, produce empty fields.
// In particular, an empty pattern on empty input produces two empty fields.
std::vector<Span> regex(std::u16string_view input,
                        std::u16string_view pattern,
                        RegexFlags flags,
                        std::optional<std::size_t> max_splits,
                        const Limits& limits);
// Optional trimming uses Unicode White_Space (ICU regex \s), retains empty
// spans, and applies resource limits to the original untrimmed clusters.
std::vector<Span> graphemes(std::u16string_view input, const Limits& limits,
                            bool trim_spaces = false);

} // namespace splitter
