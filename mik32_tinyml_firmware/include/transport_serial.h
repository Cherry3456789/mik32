#ifndef TRANSPORT_SERIAL_H
#define TRANSPORT_SERIAL_H

#include <stdint.h>
#include <stdbool.h>

void transport_init(void);
int transport_read(uint8_t *buf, uint16_t max_len);
void transport_write(const uint8_t *buf, uint16_t len);
bool transport_read_frame(uint8_t *frame_buf, uint16_t *frame_len, uint32_t timeout_ms);

#endif
