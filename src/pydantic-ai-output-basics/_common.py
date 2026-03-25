import math

import numexpr


def calculate_expression(expression: str) -> str:
    """Calculate the result of a mathematical expression."""
    try:
        result = numexpr.evaluate(
            expression.strip(),
            global_dict={},
            local_dict={"pi": math.pi, "e": math.e},
        )
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"
