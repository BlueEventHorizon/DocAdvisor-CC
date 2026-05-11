# Test Design Document

## Purpose

This document is used exclusively for doc-db functional testing.

## API Design

### TST-DES-001: Authentication Endpoint

POST /api/auth/login accepts email and password. MARKER_TEST_DES_001.

### TST-DES-002: Token Format

JWT tokens with 1-hour expiry. MARKER_TEST_DES_002.
