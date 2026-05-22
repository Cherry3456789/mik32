#ifndef TINYML_RUNTIME_H
#define TINYML_RUNTIME_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t input_bytes;
    uint16_t output_bytes;
} tinyml_shape_t;

bool tinyml_init(tinyml_shape_t *shape);
bool tinyml_infer(const uint8_t *input, uint16_t input_len, uint8_t *output, uint16_t *output_len);

#ifdef __cplusplus
}
#endif

#endif