# -*- coding: utf-8 -*-
#
#  config.py
#  proj
#

from typing import Optional
from dataclasses import dataclass
from os import path

import yaml

from proj import fs


DEFAULT_CONFIG_PATH = "~/.proj.yml"


@dataclass
class Config:
    archive_dir: str = "_archive"
    compression: bool = False
    compression_format: Optional[str] = None

    @classmethod
    def autoload(cls) -> "Config":
        filename = cls._get_config_file()
        return cls.load(filename)

    @classmethod
    def load(cls, filename: str) -> "Config":
        with open(filename) as istream:
            doc = yaml.safe_load(istream)
            return cls(**doc)

    def save(self, filename: str) -> None:
        record = {
            "archive_dir": self.archive_dir,
            "compression": self.compression,
            "compression_format": self.compression_format,
        }
        with open(filename, "w") as ostream:
            yaml.dump(record, ostream)

    @staticmethod
    def _get_config_file() -> str:
        filename = path.expanduser(DEFAULT_CONFIG_PATH)
        if not path.exists(filename):
            raise NoConfigError()

        return filename

    @property
    def compression_ext(self) -> str:
        if not self.compression_format:
            raise KeyError("no compression format selected")

        return fs.SUPPORTED_FORMATS[self.compression_format]


class NoConfigError(Exception):
    pass
