set default-list := true

mod hack 'isa/hack/justfile'
mod site 'site/justfile'

# Install the pinned project-local Sail binary.
install:
    python tools/install_sail.py

# Run global tool tests and every ISA module's regression suite.
test:
    python -m pytest tests
    just hack test

# Remove build artifacts for every registered module.
clean-all:
    just hack clean
    just site clean
