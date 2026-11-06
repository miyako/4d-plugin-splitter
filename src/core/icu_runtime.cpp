#include "icu_runtime.hpp"

#include <unicode/uclean.h>
#include <unicode/udata.h>

#include <fstream>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>

namespace splitter {
namespace {

struct AlignedDelete {
    void operator()(std::byte* pointer) const noexcept
    {
        ::operator delete(pointer, std::align_val_t(16));
    }
};

std::once_flag initialized;
std::unique_ptr<std::byte, AlignedDelete> data;

}

void initialize_icu(const std::filesystem::path& data_file)
{
    std::call_once(initialized, [&] {
        UErrorCode status = U_ZERO_ERROR;
        if (!data) {
            std::ifstream input(data_file, std::ios::binary | std::ios::ate);
            if (!input) {
                throw std::runtime_error("Bundled ICU data cannot be opened");
            }
            const auto size = input.tellg();
            if (size != SPLITTER_ICU_DATA_SIZE || size > 64 * 1024 * 1024) {
                throw std::runtime_error("Bundled ICU data has an invalid size");
            }
            auto buffer = std::unique_ptr<std::byte, AlignedDelete>(
                static_cast<std::byte*>(::operator new(static_cast<std::size_t>(size),
                                                      std::align_val_t(16))));
            input.seekg(0);
            input.read(reinterpret_cast<char*>(buffer.get()), size);
            if (!input || input.gcount() != size) {
                throw std::runtime_error("Bundled ICU data cannot be read completely");
            }
            udata_setFileAccess(UDATA_NO_FILES, &status);
            udata_setCommonData(buffer.get(), &status);
            if (U_FAILURE(status)) {
                throw std::runtime_error("Bundled ICU data cannot be registered");
            }
            // Registration retains the pointer, even if subsequent initialization fails.
            data = std::move(buffer);
        }
        u_init(&status);
        if (U_FAILURE(status)) {
            throw std::runtime_error("Bundled ICU initialization failed");
        }
    });
}

}
