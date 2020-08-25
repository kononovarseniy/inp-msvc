def code_to_float(code: int, max_code: int, min_value: float, max_value: float) -> float:
    if min_value >= max_value:
        raise ValueError(f'min_value should be strictly less than max_value. '
                         f'(min_value = {min_value}, max_value = {max_value})')
    if max_code <= 0:
        raise ValueError(f'max_code should be strictly greater than 0. (max_code = {max_code})')
    return min_value + code / max_code * (max_value - min_value)


def float_to_code(value: float, max_code: int, min_value: float, max_value: float) -> int:
    if min_value >= max_value:
        raise ValueError(f'min_value should be strictly less than max_value. '
                         f'(min_value = {min_value}, max_value = {max_value})')
    if max_code <= 0:
        raise ValueError(f'max_code should be strictly greater than 0. (max_code = {max_code})')
    return round((value - min_value) / (max_value - min_value) * max_code)
