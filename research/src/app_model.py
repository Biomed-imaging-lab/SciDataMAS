from typing import Dict, List

from data_model.datalake import Datalake
from datalake_driver.i_driver import IDriver
from datalake_driver.drivers.clearml_driver import ClearMLDriver
from datalake_driver.drivers.local_storage_driver import LocalDriver


def driver_factory(driver_conf: str) -> IDriver:
    __DRIVER_TYPE_FIELD = "driver_type"
    __DRIVER_CONF_FIELD = "driver_conf"
    if __DRIVER_TYPE_FIELD not in driver_conf.keys():
        raise RuntimeError(f"There is no '{__DRIVER_TYPE_FIELD}' in conf!")

    conf_type = driver_conf[__DRIVER_TYPE_FIELD]
    match conf_type:
        case "local":
            return LocalDriver(**driver_conf[__DRIVER_CONF_FIELD])
        case "clearml":
            return ClearMLDriver(**driver_conf[__DRIVER_CONF_FIELD])
        case _:
            return None


class AppModel:
    ### vars
    __datalake: Datalake = None

    ### consts
    __DATASET_NAME_FIELD: str = "dataset_name"

    def __init__(self, conf_dict: Dict):
        idriver = driver_factory(conf_dict)
        if idriver == None:
            raise RuntimeError(
                f"Couldn't init driver using factory: check driver config. Aborting..."
            )

        if self.__DATASET_NAME_FIELD not in conf_dict.keys():
            raise RuntimeError(
                f"There is no '{self.__DATASET_NAME_FIELD}' field in datalake conf!"
            )
        datalake_name = conf_dict[self.__DATASET_NAME_FIELD]
        self.__datalake = Datalake(datalake_name, datalake_name + "/", idriver)
        return

    @property
    def datalake(self) -> Datalake:
        # TODO: not very safety, but currently its okay.
        return self.__datalake
