"""Shared JSON decision parsing for all model adapters."""

from devpilot.domain.decision import AgentDecision


def parse_decision(raw: str) -> AgentDecision:
    """Parse AgentDecision from raw LLM output.

    Handles markdown code blocks, extra text, and multi-line JSON.
    """
    import logging

    text = raw.strip()

    # Strip markdown code block wrappers
    if text.startswith("```"):
        # Remove opening ```json or ```
        lines = text.split("\n")
        # Find first line without ```
        json_lines = []
        in_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_block:
                    # Closing block - stop
                    break
                else:
                    # Opening block - skip this line
                    in_block = True
                    continue
            if in_block or not json_lines:
                json_lines.append(line)
        if json_lines:
            text = "\n".join(json_lines).strip()

    # Try direct parse first
    try:
        return AgentDecision.model_validate_json(text)
    except Exception:
        pass

    # Try to extract the first JSON object from the text
    start = text.find("{")
    if start == -1:
        logging.error("No JSON object found in LLM response")
        raise ValueError("No JSON object found in LLM response")

    # Find matching closing brace
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    json_str = text[start:end]
    try:
        return AgentDecision.model_validate_json(json_str)
    except Exception as exc:
        logging.error("Failed to parse AgentDecision (response contents omitted)")
        raise ValueError("Failed to parse AgentDecision") from exc
