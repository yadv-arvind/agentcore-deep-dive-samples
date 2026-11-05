from pydantic import BaseModel


class Task(BaseModel):
    title: str
    files: list[str]
    acceptance: str


class Spec(BaseModel):
    requirements: list[str]
    design: str
    tasks: list[Task]
