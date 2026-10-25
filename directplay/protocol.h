/* SPDX-License-Identifier: MIT */
#ifndef JKDP_PROTOCOL_H
#define JKDP_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
#define JKDP_MAX_RAW 2052u
/* Translate mode-specific management layouts. On error packet and length
 * are unchanged. JK1.00 roster field order is independently verified;
 * the existing MotS mapping is retained pending separate verification. */
int jkdp_translate(uint8_t *raw,size_t *bytes,size_t capacity,uint32_t host_id,int to_retail,int mots);
#endif
