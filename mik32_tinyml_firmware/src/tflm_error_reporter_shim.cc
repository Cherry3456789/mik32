#include "tinyml_runtime.h"

#if TINYML_USE_TFLM

#include <cstdarg>

#include "tensorflow/lite/core/api/error_reporter.h"

namespace tflite {

int ErrorReporter::Report(const char *format, ...) {
    va_list args;
    va_start(args, format);
    const int result = Report(format, args);
    va_end(args);
    return result;
}

int ErrorReporter::ReportError(void *, const char *format, ...) {
    va_list args;
    va_start(args, format);
    const int result = Report(format, args);
    va_end(args);
    return result;
}

}  // namespace tflite

#endif  // TINYML_USE_TFLM