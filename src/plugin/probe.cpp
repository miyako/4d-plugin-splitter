#include "4DPluginAPI.h"
#include <algorithm>
#include <cstdio>

namespace {

bool equalCollections(PA_CollectionRef left, PA_CollectionRef right)
{
    const auto count = PA_GetCollectionLength(left);
    if (count != PA_GetCollectionLength(right)) {
        return false;
    }
    for (PA_long32 index = 0; index < count; ++index) {
        PA_Variable a = PA_GetCollectionElement(left, index);
        PA_Variable b = PA_GetCollectionElement(right, index);
        bool equal = PA_GetVariableKind(a) == eVK_Unistring &&
                     PA_GetVariableKind(b) == eVK_Unistring;
        if (equal) {
            PA_Unistring x = PA_GetStringVariable(a);
            PA_Unistring y = PA_GetStringVariable(b);
            const auto length = PA_GetUnistringLength(&x);
            equal = length == PA_GetUnistringLength(&y);
            if (equal && length != 0) {
                equal = std::equal(PA_GetUnistring(&x), PA_GetUnistring(&x) + length,
                                   PA_GetUnistring(&y));
            }
        }
        PA_ClearVariable(&a);
        PA_ClearVariable(&b);
        if (!equal) {
            return false;
        }
    }
    return true;
}

void delegateSplit(PA_PluginParameters params, bool variantSeparator, bool variantOptions,
                   bool traceOptions = true)
{
    PA_Variable arguments[3]{};
    PA_SetStringVariable(&arguments[0], PA_GetStringParameter(params, 1));
    if (variantSeparator) {
        arguments[1] = PA_GetVariableParameter(params, 2);
    } else {
        PA_SetStringVariable(&arguments[1], PA_GetStringParameter(params, 2));
    }
    if (variantOptions) {
        arguments[2] = PA_GetVariableParameter(params, 3);
        if (PA_GetVariableKind(arguments[2]) == eVK_Undefined) {
            PA_SetLongintVariable(&arguments[2], 0);
        }
    } else {
        const auto options = PA_GetLongParameter(params, 3);
        if (traceOptions) {
            std::fprintf(stderr, "SPLITTER_LONG_OPTIONS=%d\n", options);
        }
        PA_SetLongintVariable(&arguments[2], options);
    }
    PA_Variable result = PA_ExecuteCommandByID(1554, arguments, 3);
    if (PA_GetLastError() != eER_NoErr ||
        PA_GetVariableKind(result) != eVK_Collection) {
        std::fprintf(stderr, "SPLITTER_DELEGATE_FAILED status=%d\n", PA_GetLastError());
        return;
    }
    // Transfer the result reference to the caller; do not clear it here.
    PA_ReturnCollection(params, PA_GetCollectionVariable(result));
}

}

void PluginMain(PA_long32 selector, PA_PluginParameters params)
{
    if (selector == 1) {
        delegateSplit(params, true, true);
    } else if (selector == 2) {
        PA_Variable arguments[2]{};
        PA_SetLongintVariable(&arguments[0], 50001);
        PA_Unichar message[] = {'S', 'p', 'l', 'i', 't', 't', 'e', 'r', 0};
        PA_Unistring text = PA_CreateUnistring(message);
        PA_SetStringVariable(&arguments[1], &text);
        PA_ExecuteCommandByID(1805, arguments, 2);
        std::fprintf(stderr, "SPLITTER_THROW status=%d\n", PA_GetLastError());
        PA_DisposeUnistring(&text);
    } else if (selector == 3) {
        PA_CollectionRef result = PA_CreateCollection();
        for (short index = 1; index <= 2; ++index) {
            PA_Variable value{};
            PA_SetLongintVariable(&value,
                                 PA_GetVariableKind(PA_GetVariableParameter(params, index)));
            PA_SetCollectionElement(result, index - 1, value);
        }
        PA_ReturnCollection(params, result);
    } else if (selector == 4) {
        PA_ReturnLong(params, equalCollections(PA_GetCollectionParameter(params, 1),
                                              PA_GetCollectionParameter(params, 2)));
    } else if (selector == 5) {
        PA_Variable arguments[3]{};
        PA_SetStringVariable(&arguments[0], PA_GetStringParameter(params, 1));
        PA_SetLongintVariable(&arguments[1], PA_GetLongParameter(params, 2));
        PA_SetLongintVariable(&arguments[2], PA_GetLongParameter(params, 3));
        PA_Variable value = PA_ExecuteCommandByID(12, arguments, 3);
        if (PA_GetLastError() != eER_NoErr) {
            std::fprintf(stderr, "SPLITTER_SPAN_FAILED status=%d\n", PA_GetLastError());
            return;
        }
        PA_CollectionRef result = PA_CreateCollection();
        PA_SetCollectionElement(result, 0, value);
        PA_ClearVariable(&value);
        PA_ReturnCollection(params, result);
    } else if (selector == 6) {
        delegateSplit(params, true, false);
    } else if (selector == 7) {
        delegateSplit(params, false, false);
    } else if (selector == 8) {
        delegateSplit(params, false, true);
    } else if (selector == 9) {
        std::fprintf(stderr, "SPLITTER_FOURTH_KIND=%d\n",
                     PA_GetVariableKind(PA_GetVariableParameter(params, 4)));
        delegateSplit(params, false, false);
    } else if (selector == 10) {
        std::fprintf(stderr, "SPLITTER_FOURTH_OBJECT_NULL=%d\n",
                     PA_GetObjectParameter(params, 4) == nullptr);
        delegateSplit(params, false, false);
    } else if (selector == 11) {
        std::fprintf(stderr, "SPLITTER_FOURTH_COLLECTION_NULL=%d\n",
                     PA_GetCollectionParameter(params, 4) == nullptr);
        delegateSplit(params, false, false);
    } else if (selector == 12) {
        PA_Variable arguments[2]{};
        PA_SetBooleanVariable(&arguments[0], false);
        PA_Unichar message[] = {'S', 'p', 'l', 'i', 't', 't', 'e', 'r', 0};
        PA_Unistring text = PA_CreateUnistring(message);
        PA_SetStringVariable(&arguments[1], &text);
        PA_ExecuteCommandByID(1129, arguments, 2);
        std::fprintf(stderr, "SPLITTER_ASSERT status=%d\n", PA_GetLastError());
        PA_DisposeUnistring(&text);
    } else if (selector == 13) {
        PA_ReturnCollection(params, nullptr);
    } else if (selector == 14) {
        delegateSplit(params, false, false, false);
    }
}
