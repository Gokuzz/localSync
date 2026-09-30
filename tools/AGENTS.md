# Tools Agent Instructions

This directory is for development and test utilities.

Tools must not become hidden production dependencies. If production code starts depending on a tool, promote the dependency explicitly into the relevant application module and document the decision.

The fake phone tool should simulate a generic device client for protocol testing. Keep it platform-neutral; it should not encode Android-only protocol assumptions.
