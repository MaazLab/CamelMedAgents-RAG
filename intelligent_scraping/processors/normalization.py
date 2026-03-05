def normalize_age_group(age: int):
    if age is None:
        return None
    if age < 13:
        return "child"
    if age < 18:
        return "adolescent"
    if age < 65:
        return "adult"
    return "elderly"