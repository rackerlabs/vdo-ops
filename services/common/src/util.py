def strip_prefix(str, pre):
    if str.startswith(pre):
        return str[len(pre) :]
    return str
