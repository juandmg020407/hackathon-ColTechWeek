"""Errors raised by domain rules."""


class DomainError(ValueError):
    """A business rule was violated."""


class IncompatibleNPKBasis(DomainError):
    """An input uses a nutrient convention that the elemental core cannot mix."""


class ValidationRequired(DomainError):
    """There is not enough validated evidence for a responsible prescription."""
