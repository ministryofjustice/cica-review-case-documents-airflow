"""Sentence boundary detection logic for chunking."""


class SentenceDetector:
    """Detects sentence boundaries in text."""

    @staticmethod
    def ends_with_sentence_terminator(text: str) -> bool:
        """Check if text ends with a sentence terminator.

        Args:
            text: Text to check

        Returns:
            True if text ends with . ? or !
        """
        # Strip trailing whitespace and check last character
        text = text.rstrip()
        if not text:
            return False

        # Check for sentence-ending punctuation
        return text[-1] in {".", "?", "!"}
