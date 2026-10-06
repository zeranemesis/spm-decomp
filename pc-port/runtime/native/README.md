# SPM native overrides

This directory is intentionally empty at first.

WiiCompiled scans the configured native source directory for address-based HLE/native override registrations.
The upstream runtime contains Mario Kart Wii-specific registrations, which must not suppress unrelated
Super Paper Mario functions merely because an address happens to overlap.

SPM-specific native/HLE bridges will be added here only after their symbols and ABI have been verified.
