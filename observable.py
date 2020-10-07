from typing import TypeVar, Generic, Callable, List

T = TypeVar('T')

Observer = Callable[['Observable[T]'], None]


class Observable(Generic[T]):
    """An implementation of an "observable" pattern used by GUI widgets to subscribe to variable changes."""

    _value: T
    _observers: List[Observer]

    def __init__(self, value: T):
        self._value = value
        self._observers = []

    def add_observer(self, observer: Observer) -> None:
        self._observers.append(observer)

    def remove_observer(self, observer: Observer) -> None:
        self._observers.remove(observer)

    @property
    def value(self) -> T:
        return self._value

    @value.setter
    def value(self, value: T) -> None:
        self._value = value
        for o in self._observers:
            o(self)
