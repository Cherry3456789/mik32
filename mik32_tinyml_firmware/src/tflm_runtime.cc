#include "tinyml_runtime.h"

#if TINYML_USE_TFLM

#include <cstring>

#include "model_data.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

#ifndef TINYML_TENSOR_ARENA_BYTES
#define TINYML_TENSOR_ARENA_BYTES 8192
#endif

namespace {

alignas(16) uint8_t tensor_arena[TINYML_TENSOR_ARENA_BYTES];

const tflite::Model *model = nullptr;
tflite::MicroInterpreter *interpreter = nullptr;
TfLiteTensor *input_tensor = nullptr;
TfLiteTensor *output_tensor = nullptr;

using OpResolver = tflite::MicroMutableOpResolver<8>;

bool add_model_ops(OpResolver *resolver) {
    if (resolver == nullptr) {
        return false;
    }

    // Keep this resolver intentionally small. Add operations here when
    // model-info shows a model needs them.
    return resolver->AddFullyConnected() == kTfLiteOk &&
           resolver->AddReshape() == kTfLiteOk &&
           resolver->AddSoftmax() == kTfLiteOk &&
           resolver->AddQuantize() == kTfLiteOk &&
           resolver->AddDequantize() == kTfLiteOk;
}

}  // namespace

extern "C" bool tinyml_init(tinyml_shape_t *shape) {
    if (shape == nullptr || model_data_len == 0) {
        return false;
    }

    model = tflite::GetModel(model_data);
    if (model == nullptr || model->version() != TFLITE_SCHEMA_VERSION) {
        return false;
    }

    static OpResolver resolver;
    if (!add_model_ops(&resolver)) {
        return false;
    }

    static tflite::MicroInterpreter static_interpreter(
        model,
        resolver,
        tensor_arena,
        TINYML_TENSOR_ARENA_BYTES
    );
    interpreter = &static_interpreter;

    if (interpreter->AllocateTensors() != kTfLiteOk) {
        return false;
    }

    input_tensor = interpreter->input(0);
    output_tensor = interpreter->output(0);
    if (input_tensor == nullptr || output_tensor == nullptr) {
        return false;
    }
    if (input_tensor->bytes > 0xFFFFu || output_tensor->bytes > 0xFFFFu) {
        return false;
    }

    shape->input_bytes = static_cast<uint16_t>(input_tensor->bytes);
    shape->output_bytes = static_cast<uint16_t>(output_tensor->bytes);
    return true;
}

extern "C" bool tinyml_infer(const uint8_t *input, uint16_t input_len, uint8_t *output, uint16_t *output_len) {
    if (input == nullptr || output == nullptr || output_len == nullptr ||
        interpreter == nullptr || input_tensor == nullptr || output_tensor == nullptr) {
        return false;
    }
    if (input_len != input_tensor->bytes || *output_len < output_tensor->bytes) {
        return false;
    }

    std::memcpy(input_tensor->data.uint8, input, input_tensor->bytes);
    if (interpreter->Invoke() != kTfLiteOk) {
        return false;
    }

    std::memcpy(output, output_tensor->data.uint8, output_tensor->bytes);
    *output_len = static_cast<uint16_t>(output_tensor->bytes);
    return true;
}

#endif  // TINYML_USE_TFLM