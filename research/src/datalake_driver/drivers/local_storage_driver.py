import os

from datalake_driver.i_driver import IDriver


class LocalDriver(IDriver):
    """
    Implementing driver model for local storaging
    """

    # vars
    __root_folder: str = None

    # consts
    __ROOT_FOLDER_ARG = "root_folder"

    def __init__(self, **kwargs):
        # section 1 - checking
        if self.__ROOT_FOLDER_ARG not in kwargs.keys():
            raise ValueError(
                f"There is no '{self.__ROOT_FOLDER_ARG}' value in constructor."
            )


        root_folder = kwargs[self.__ROOT_FOLDER_ARG]
        if os.path.exists(root_folder) == False:
            raise ValueError(
                f"The folder in such path '{root_folder}' doesn't exist!"
            )

        # section 2 - initing
        self.__root_folder = root_folder
        return

    def write(self, file: bytearray, filename: str, cataloque: str) -> None:
        """
        Writes (register) file in driver file storaging system

        :param origin_str: original path of file in system
        :type file: bytearray
        :param filename: key of file in a storage (u can think about it as a filename)
        :type filename: str
        :param cataloque: path to cataloque where file should be stored
        :type cataloque: str
        """

        full_path = os.path.join(self.__root_folder, cataloque, filename)
        with open(full_path, "wb") as fileIO:
            fileIO.write(file)
        return

    def get(self, filename: str, cataloque: str) -> bytearray:
        """
        Retrive file from storage by its key/name.
        Call exception if there are no file with such key

        :param filename: name of file
        :type filename: str
        :param cataloque: path to cataloque where file should be stored
        :type cataloque: str
        :return: filename
        :rtype: bytearray
        """
        full_path = os.path.join(self.__root_folder, cataloque, filename)
        if os.path.exists(full_path) == False:
            raise ValueError(f"There is no file with path '{full_path}'")

        with open(full_path, "rb") as fileIO:
            bytearr = fileIO.read()
            bytearray_memory = bytearray(bytearr)
        return bytearray_memory

    def is_exist(self, key: str, cataloque: str) -> bool:
        """
        Finding is exist file with such key in storage

        :param filename: name of file
        :type filename: str
        :param cataloque: path to cataloque where file should be stored
        :type cataloque: str
        :return: Is storage contains the file with passed key (true - yes, contains; no - doesn't contain)
        :rtype: bool
        """
        return os.path.exists(os.path.join(self.__root_folder, cataloque, key))

    def create_cataloque(self, cat_name: str) -> None:
        full_path = os.path.join(self.__root_folder, cat_name)
        os.makedirs(full_path, exist_ok=True)
        return

    def is_cataloque_exists(self, cat_name: str) -> bool:
        full_path = os.path.join(self.__root_folder, cat_name)
        if os.path.exists(full_path):
            return True
        else:
            return False
