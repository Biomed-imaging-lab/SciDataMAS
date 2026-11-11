from abc import ABC, abstractmethod


class IDriver(ABC):
    """
    Implements storaging procedures for different cataloquable data storages. Main operations:
    - register_file: storage file in system
    - read_file: retrieving file from system

    TODO list:
    - Storages can be not `cataloguable` - they can generate key of file in runtime. We should support it with different method and
    'name'-'key' mapping procedure
    - Make 'remove'-oriented operations - remove file, remove cataloque
    """

    def __init__(self, **kwargs):
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def create_cataloque(self, cat_name: str) -> None:
        pass

    @abstractmethod
    def is_cataloque_exists(self, cat_name: str) -> bool:
        pass
