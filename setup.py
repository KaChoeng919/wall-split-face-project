# setup.py: 套件安裝配置
from setuptools import setup, find_packages

setup(
    name='wall_split_face',
    version='1.0.0',
    packages=find_packages(),
    description='Revit Dynamo腳本：自動分割牆體面基於房間高度',
    author='Your Name',
    author_email='your.email@example.com',
    install_requires=[],  # 無第三方依賴
    classifiers=[
        'Programming Language :: Python :: 2.7',  # IronPython 2.7相容
    ],
)
