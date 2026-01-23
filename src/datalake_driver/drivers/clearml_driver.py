import os
import tempfile

from clearml import Dataset, StorageManager, Task, TaskTypes
from clearml.backend_api.session.client import APIClient

from datalake_driver.i_driver import IDriver


class ClearMLDriver(IDriver):
    """
    Implementing driver model for ClearML storaging.
    """

    ### vars
    __root_project: str = None

    ### consts
    # main
    __ROOT_PROJ_NAME: str = "root_proj"
    __INIT_CATALOGUE_TASK_NAME: str = "Creating catalogue"

    def __init__(self, **kwargs):
        # section 1 - checking
        if self.__ROOT_PROJ_NAME not in kwargs.keys():
            raise ValueError(
                f"There is no '{self.__ROOT_PROJ_NAME}' value in constructor."
            )

        # section 2 - initing
        self.__root_project = kwargs[self.__ROOT_PROJ_NAME]

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
        cataloque = self.__root_project.rstrip("/") + "/" + cataloque.rstrip("/")
        cataloque_elems = cataloque.split("/")

        proj_catalogue = "/".join(cataloque_elems[0:-1])
        leaf_prof = cataloque_elems[-1]

        try:
            existing_dataset = Dataset.get(
                dataset_name=leaf_prof, dataset_project=proj_catalogue
            )
            existing_datasets = [existing_dataset]
        except Exception as e:
            existing_datasets = []

        dataset = Dataset.create(
            dataset_name=leaf_prof,
            dataset_project=proj_catalogue,
            parent_datasets=existing_datasets,
        )

        with tempfile.TemporaryDirectory() as temp_root:
            local_file_path = os.path.join(temp_root, filename)

            with open(local_file_path, "wb") as f:
                f.write(file)

            print(local_file_path, filename)
            dataset.add_files(path=local_file_path)

            dataset.upload()
            dataset.finalize()

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

        cataloque = self.__root_project.rstrip("/") + "/" + cataloque.rstrip("/")
        cataloque_elems = cataloque.split("/")

        proj_catalogue = "/".join(cataloque_elems[0:-1])
        leaf_prof = cataloque_elems[-1]

        dataset = Dataset.get(dataset_name=leaf_prof, dataset_project=proj_catalogue)

        with tempfile.TemporaryDirectory() as temp_dir:
            local_folder = dataset.get_mutable_local_copy(target_folder=temp_dir)
            specific_file_path = os.path.join(local_folder, filename)
            if (
                os.path.exists(specific_file_path)
                and os.path.isfile(specific_file_path)
            ) == False:
                raise RuntimeError(
                    f"There is no file with name '{filename}' in dataset!"
                )

            with open(specific_file_path, "rb") as fileIO:
                filebytes = bytearray(fileIO.read())
        return filebytes

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

        cataloque = self.__root_project.rstrip("/") + "/" + cataloque.rstrip("/")
        cataloque_elems = cataloque.split("/")

        proj_catalogue = "/".join(cataloque_elems[0:-1])
        leaf_prof = cataloque_elems[-1]

        dataset = Dataset.get(dataset_name=leaf_prof, dataset_project=proj_catalogue)

        file_entries_dict = dataset.file_entries_dict
        if key in file_entries_dict.keys():
            return True
        else:
            return False

    def create_cataloque(self, cat_name: str) -> None:
        # To make not a lot of tasks
        if self.is_cataloque_exists(cat_name) == True:
            return

        # We are creating proj with creating synthetic task. Not straight forward solution - but tracable and easy.
        full_cat_path = self.__root_project.rstrip("/") + "/" + cat_name.rstrip("/")

        dummy_task = Task.init(
            project_name=full_cat_path,
            task_name=self.__INIT_CATALOGUE_TASK_NAME + f" '{cat_name}'",
            task_type=TaskTypes.custom,
            reuse_last_task_id=False,
            auto_connect_frameworks=False,
            auto_connect_arg_parser=False,
            auto_resource_monitoring=False,
            auto_connect_streams=False,
        )
        dummy_task.close()
        return

    def is_cataloque_exists(self, cat_name: str) -> bool:
        client = APIClient()

        all_projects_response = client.projects.get_all(shallow_search=False)
        all_project_names = [proj.name for proj in all_projects_response]

        search_target = self.__root_project.rstrip("/") + "/" + cat_name.rstrip("/")

        for existing_path in all_project_names:
            existing_path = existing_path.rstrip("/")

            if search_target == existing_path:
                return True

            if existing_path.startswith(search_target + "/"):
                return True

        return False
