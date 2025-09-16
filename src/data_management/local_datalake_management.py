import json
import os
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from data_management.local_dataset_management import LocalRichDataset


class DatasetInfo(BaseModel):
    name: str = Field(description="The name of dataset", default="")
    full_description: str = Field(
        description="The bird's-eye description of dataset", default=""
    )


class LocalDataLake:
    __INFO_FILENAME = "datalake_info.json"

    def __init__(self, local_full_path: str):
        self.__datalakes = {}
        self.__local_full_path = local_full_path
        return

    def __save_text_log(self):
        datalakes_paths = {
            name: datalake.get_path() for name, datalake in self.__datalakes.items()
        }
        with open(
            os.path.join(self.__local_full_path, LocalDataLake.__INFO_FILENAME), "w"
        ) as io_file:
            json.dump(datalakes_paths, io_file)
        return

    def save_current_status(self):
        self.__save_text_log()

        for _, datalake in self.__datalakes.items():
            datalake.save_datalake()
        return

    @staticmethod
    def create(storage_name: str, storage_path: str = "./"):
        # 0 - tests block before creation data storage
        if not os.path.exists(storage_path):
            raise FileNotFoundError(
                f"The folder for storage '{storage_path}' does not exist."
            )

        if os.path.isfile(storage_path):
            raise NotADirectoryError(
                f"The path '{storage_path}' leads to a file, not a folder!"
            )

        full_path = os.path.join(storage_path, storage_name)
        if os.path.exists(full_path):
            raise FileExistsError(
                f"The data storage with name '{storage_name}' in '{storage_path}' alreafy exists! Try to change name or path."
            )

        # 1 - creating folder for a data storage with some info files
        os.mkdir(full_path)

        # 2 - create instance and fill with correct data
        local_storage = LocalDataLake(full_path)
        local_storage.save_current_status()
        return local_storage

    def __load_info(self) -> Dict[str, Any]:
        with open(
            os.path.join(self.__local_full_path, LocalDataLake.__INFO_FILENAME), "r"
        ) as io_file:
            datasets_placement_info = json.load(io_file)
        return datasets_placement_info

    @staticmethod
    def open(storage_full_path: str):
        # 0 - make all checks
        if not os.path.exists(storage_full_path):
            raise FileNotFoundError(
                f"The folder with possible storage '{storage_full_path}' does not exist."
            )

        if os.path.isfile(storage_full_path):
            raise NotADirectoryError(
                f"The path '{storage_full_path}' leads to a file, not a folder!"
            )

        full_path = os.path.join(storage_full_path, LocalDataLake.__INFO_FILENAME)
        if not os.path.exists(full_path):
            raise FileExistsError(
                f"The expected file with info '{LocalDataLake.__INFO_FILENAME}' doesn't exist in '{storage_full_path}'!"
            )

        # 1 - read text info about local data storage
        local_datalake_instance = LocalDataLake(storage_full_path)
        datasets_placement_info = local_datalake_instance.__load_info()

        for dataset_name, dataset_path in datasets_placement_info.items():
            opened_dataset = LocalRichDataset.read(dataset_path)
            local_datalake_instance.__datalakes.update({dataset_name: opened_dataset})

        return local_datalake_instance

    def create_dataset(
        self,
        name: str,
        description: str,
        dataset_meta_schema: Dict[str, Dict[str, str]],
    ) -> None:
        # 0 - make checks about that datalake could be created
        if name in self.__datalakes.keys():
            raise ValueError(
                f"Can't create dataset in datalake with name '{name}' - some dataset with the same name already exists!"
            )

        # 1 - create folder for new dataset
        new_dataset = LocalRichDataset.create(
            folder_path=self.__local_full_path,
            name=name,
            descr=description,
            pre_capturing_metadata_schema=dataset_meta_schema,
        )

        # 2 - log datalake if all is good
        self.__datalakes.update({name: new_dataset})
        self.save_current_status()
        return

    def get_datalake_info(self) -> List[DatasetInfo]:
        result_list = []
        for name, dataset in self.__datalakes.items():
            new_info = DatasetInfo()
            new_info.name = name
            new_info.full_description = dataset.get_string_base_info()
            result_list.append(new_info)
        return result_list

    def __getitem__(self, key: str) -> LocalRichDataset:
        return self.__datalakes[key]
