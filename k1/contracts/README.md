# K1 Contracts System

This directory contains the K1 kernel's contract system, implementing a wiring-first architecture for module connectivity validation.

## Structure

- `schemas/`: Canonical contract schemas
- `registry/`: Runtime registries
- `loaders/`: Contract loading and resolution
- `validators/`: Static and graph validation
- `graph/`: Wiring graph model
- `manifest/`: Compiled manifest
- `runtime/`: Runtime enforcement
- `generators/`: Development tools
- `reports/`: Validation outputs

## Usage

Run validation: `python -m k1.contracts`
