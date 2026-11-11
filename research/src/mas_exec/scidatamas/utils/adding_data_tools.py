from langchain_core.tools import StructuredTool


def read_txt_file(path: str) -> str:
    """
    Reading some file function and returns it's content.

    Args:
        path (str): The path to not-binary file.

    Returns:
        str: the content of read file.
    """
    try:
        with open(path, "rt") as i_stream:
            content = i_stream.read()
        return content
    except Exception as exp:
        return f"There was an exception during file reading:\n'{str(exp)}'"


BASIC_TOOLS = [
    StructuredTool.from_function(read_txt_file, name="read_file", parse_docstring=True)
]
