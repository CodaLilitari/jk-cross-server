/* SPDX-License-Identifier: MIT */
#ifndef JKDP_PROTOCOL_H
#define JKDP_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
#define JKDP_MAX_RAW 2052u
/* Translate only documented management layouts. On error packet and length
 * are unchanged. Both original JK1.00 and MotS use the same roster layout. */
int jkdp_translate(uint8_t *raw,size_t *bytes,size_t capacity,uint32_t host_id,int to_retail,int mots);
#endif
