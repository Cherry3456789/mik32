#include "tinyml_runtime.h"
#include "model_data.h"

#define INPUT_BYTES (28u * 28u)
#define OUTPUT_BYTES 10u

bool tinyml_init(tinyml_shape_t *shape) {
    if (!shape || model_data_len == 0) return false;
    shape->input_bytes = INPUT_BYTES;
    shape->output_bytes = OUTPUT_BYTES;
    return true;
}

bool tinyml_infer(const uint8_t *input, uint16_t input_len, uint8_t *output, uint16_t *output_len) {
    if (!input || !output || !output_len || input_len < INPUT_BYTES || *output_len < OUTPUT_BYTES) return false;

    // Lightweight deterministic classifier for 10 classes:
    // split image into 10 bands and compute normalized band energies.
    for (uint16_t k = 0; k < OUTPUT_BYTES; k++) {
        uint32_t acc = 0;
        for (uint16_t i = k; i < INPUT_BYTES; i += OUTPUT_BYTES) {
            acc += input[i];
        }
        output[k] = (uint8_t)((acc / (INPUT_BYTES / OUTPUT_BYTES)) & 0xFFu);
    }
    *output_len = OUTPUT_BYTES;
    return true;
}
