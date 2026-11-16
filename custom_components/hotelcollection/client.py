"""Async TCP client for the diffuser's local port (8080)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .codec import (
    TYPE_READ,
    TYPE_WRITE,
    Frame,
    FrameParser,
    read_request,
    write_request,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5
REPLY_TIMEOUT = 3


class HotelCollectionError(Exception):
    """Communication failure."""


class HotelCollectionClient:
    """Keeps one persistent connection, dispatches every frame to a callback,
    and lets callers await specific replies."""

    def __init__(self, host: str, port: int, on_frame: Callable[[Frame], None] | None = None) -> None:
        self.host = host
        self.port = port
        self._on_frame = on_frame
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._parser = FrameParser()
        self._waiters: list[tuple[int, int, asyncio.Future]] = []
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise HotelCollectionError(f"Cannot connect to {self.host}:{self.port}: {err}") from err
        self._parser = FrameParser()
        self._task = asyncio.get_running_loop().create_task(self._read_loop())
        _LOGGER.debug("Connected to %s:%s", self.host, self.port)

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        self._writer = self._reader = None
        self._fail_waiters(HotelCollectionError("Connection closed"))

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                data = await self._reader.read(1024)
                if not data:
                    break
                for frame in self._parser.feed(data):
                    _LOGGER.debug("RX %r", frame)
                    self._resolve_waiters(frame)
                    if self._on_frame:
                        try:
                            self._on_frame(frame)
                        except Exception:  # noqa: BLE001
                            _LOGGER.exception("Frame callback failed")
        except asyncio.CancelledError:
            raise
        except OSError as err:
            _LOGGER.debug("Read error: %s", err)
        _LOGGER.debug("Connection to %s lost", self.host)
        if self._writer:
            self._writer.close()
        self._writer = self._reader = None
        self._fail_waiters(HotelCollectionError("Connection lost"))

    def _resolve_waiters(self, frame: Frame) -> None:
        for item in list(self._waiters):
            ftype, cmd, fut = item
            if frame.ftype == ftype and frame.cmd == cmd and not fut.done():
                fut.set_result(frame)
                self._waiters.remove(item)

    def _fail_waiters(self, err: Exception) -> None:
        for _, _, fut in self._waiters:
            if not fut.done():
                fut.set_exception(err)
        self._waiters.clear()

    async def _exchange(self, data: bytes, ftype: int, cmd: int) -> Frame:
        async with self._lock:
            await self.connect()
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            self._waiters.append((ftype, cmd, fut))
            assert self._writer is not None
            _LOGGER.debug("TX %s", data.hex(" "))
            self._writer.write(data)
            try:
                await self._writer.drain()
                return await asyncio.wait_for(fut, REPLY_TIMEOUT)
            except (OSError, asyncio.TimeoutError) as err:
                if (ftype, cmd, fut) in self._waiters:
                    self._waiters.remove((ftype, cmd, fut))
                raise HotelCollectionError(f"No reply to cmd {cmd:02X}: {err!r}") from err

    async def read(self, cmd: int) -> Frame:
        """Send a read request and return the matching R reply."""
        return await self._exchange(read_request(cmd), TYPE_READ, cmd)

    async def write(self, cmd: int, value: int) -> None:
        """Send a one-byte write and wait for its ACK."""
        await self._exchange(write_request(cmd, value), TYPE_WRITE, cmd)
