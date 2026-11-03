import re
import unicodedata
from typing import Any, Dict, List, Optional


def normalize_string(val: str) -> str:
    """Normalize text by lowercasing, stripping, removing accents and non-alphanumeric noise."""
    if not val:
        return ""
    text = str(val).strip().lower()
    # Normalize unicode to NFKD to strip accents
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Replace non-alphanumeric characters with space
    text = re.sub(r"[^\w\s]", " ", text)
    # Replace multiple whitespaces with single space
    text = re.sub(r"\s+", " ", text).strip()
    return text


class BaseAnswerValidator:
    """Base interface for question answer validators."""

    def validate(
        self,
        submitted: str,
        answer_key: str,
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        raise NotImplementedError


class ExactMatchValidator(BaseAnswerValidator):
    def validate(
        self,
        submitted: str,
        answer_key: str,
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        return str(submitted).strip() == str(answer_key).strip()


class CaseInsensitiveValidator(BaseAnswerValidator):
    def validate(
        self,
        submitted: str,
        answer_key: str,
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        return str(submitted).strip().lower() == str(answer_key).strip().lower()


class MultipleChoiceValidator(BaseAnswerValidator):
    """
    Validates multiple choice selections.
    Accepts:
    - Direct option key match (e.g. "A", "B", "C")
    - Full text match of the selected option text
    """

    def validate(
        self,
        submitted: str,
        answer_key: str,
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        sub_clean = str(submitted).strip().lower()
        key_clean = str(answer_key).strip().lower()

        # 1. Direct key match (e.g., "a" == "a")
        if sub_clean == key_clean:
            return True

        # 2. Check if submitted matches the option text corresponding to the answer_key
        if options and isinstance(options, list):
            target_text = None
            for opt in options:
                if isinstance(opt, dict):
                    opt_key = str(opt.get("key", "")).strip().lower()
                    opt_text = str(opt.get("text", "")).strip().lower()
                    if opt_key == key_clean:
                        target_text = opt_text
                    if opt_key == sub_clean and opt_key == key_clean:
                        return True
                    if opt_text and opt_text == sub_clean and opt_key == key_clean:
                        return True
                elif isinstance(opt, str):
                    if opt.strip().lower() == sub_clean and opt.strip().lower() == key_clean:
                        return True

            if target_text and sub_clean == target_text:
                return True

        return False


class NumericValidator(BaseAnswerValidator):
    """Validates numeric answers allowing float tolerance."""

    def validate(
        self,
        submitted: str,
        answer_key: str,
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        try:
            sub_num = float(re.sub(r"[^\d.-]", "", str(submitted).strip()))
            key_num = float(re.sub(r"[^\d.-]", "", str(answer_key).strip()))
            return abs(sub_num - key_num) < 1e-4
        except (ValueError, TypeError):
            return False


class RegexValidator(BaseAnswerValidator):
    """Validates submitted text against a regular expression pattern defined in answer_key."""

    def validate(
        self,
        submitted: str,
        answer_key: str,
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        try:
            pattern = re.compile(str(answer_key).strip(), re.IGNORECASE)
            return bool(pattern.search(str(submitted).strip()))
        except re.error:
            return False


class NormalizedTextValidator(BaseAnswerValidator):
    """Validates text answers by stripping punctuation, accents, and excessive spacing."""

    def validate(
        self,
        submitted: str,
        answer_key: str,
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        return normalize_string(submitted) == normalize_string(answer_key)


VALIDATOR_REGISTRY = {
    "EXACT_MATCH": ExactMatchValidator(),
    "MULTIPLE_CHOICE": MultipleChoiceValidator(),
    "CASE_INSENSITIVE": CaseInsensitiveValidator(),
    "SHORT_TEXT": CaseInsensitiveValidator(),
    "NUMERIC": NumericValidator(),
    "REGEX": RegexValidator(),
    "NORMALIZED_TEXT": NormalizedTextValidator(),
    "PUZZLE": CaseInsensitiveValidator(),
    "MEMORY": CaseInsensitiveValidator(),
    "DECODE": NormalizedTextValidator(),
}


def validate_answer(
    submitted: str,
    answer_key: str,
    validator_type: str = "EXACT_MATCH",
    options: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Validate a participant answer using the specified validator type.
    Falls back to CaseInsensitiveValidator if validator_type is unrecognized.
    """
    validator = VALIDATOR_REGISTRY.get(validator_type.upper(), CaseInsensitiveValidator())
    return validator.validate(submitted, answer_key, options=options)
