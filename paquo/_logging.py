import logging
import re
from contextlib import contextmanager, ExitStack, ContextDecorator, AbstractContextManager, suppress
from typing import Iterable, Tuple

from paquo import settings
from paquo.java import System, PrintStream, ByteArrayOutputStream, StandardCharsets, LogManager

# log level settings
LOG_LEVEL = settings.LOG_LEVEL.upper()
logging.basicConfig(level=LOG_LEVEL)
getattr(LogManager, f"set{LOG_LEVEL.title()}", lambda: None)()


class _JavaLoggingBase(AbstractContextManager):
    """reentrant logging abstraction for redirecting JVM output to python

    will currently flush logging output on exit
    """
    java_default = None  # REQUIRED IN SUBCLASSES
    java_setter = None  # REQUIRED IN SUBCLASSES
    _count = 0
    _java_buffer = None
    _logger = logging.getLogger("QUPATH")
    _java_log_entry_match = re.compile(r"""^
        (?P<timestamp>[0-9:.]+)
        [ ]\[(?P<logger>[^]]+)\]
        [ ]\[(?P<level>[^]]+)\]
        [ ](?P<origin>[^ ]+)
        [ ]-[ ](?P<msg>.*)
        $
    """, re.VERBOSE).match

    @contextmanager
    def _stop_redirection_on_error(self):
        # reuse stdio reset in case __enter__ crashes
        with ExitStack() as stack:
            stack.push(self)
            yield
            # we did not crash!
            stack.pop_all()

    def __enter__(self):
        """increase reference count and redirect stdio"""
        self._count += 1
        with self._stop_redirection_on_error():
            if self._java_buffer is None:
                java_buffer = ByteArrayOutputStream()
                ps = PrintStream(
                    java_buffer,
                    True,
                    StandardCharsets.UTF_8.name()
                )
                # note: these two lines should be made atomic
                self.java_setter(ps)
                self._java_buffer = java_buffer
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """decrease reference count and cleanup if 0"""
        self._count = max(0, self._count - 1)
        self.flush_logs()  # flush logs no matter what
        if not self._count:
            # note: these two lines should be made atomic
            self.java_setter(self.java_default)
            self._java_buffer = None

    def flush_logs(self):
        """flush the java buffer to the Logger"""
        # extract the buffer and clear it
        try:
            output = str(self._java_buffer.toString())
        except AttributeError:  # pragma: no cover
            return
        with suppress(AttributeError):
            self._java_buffer.reset()
        # assume JVM console output is one line per msg
        for (origin, level), entry in self.iter_logs(output):
            if "WARN" in level:
                self._logger.warning("%s: %s", origin, entry)
            elif "ERR" in level:
                # FIXME: SHOULD THIS RAISE AN EXCEPTION?
                self._logger.error("%s: %s", origin, entry)
            elif "DEBUG" in level:
                self._logger.debug("%s: %s", origin, entry)
            else:
                self._logger.info("%s: %s", origin, entry)

    def iter_logs(self, output: str) -> Iterable[Tuple[str, str, str, str]]:
        entry = []
        info = ('NONE', 'NONE')
        for line in output.splitlines(keepends=True):
            if not line.strip():
                continue  # pragma: no cover
            m = self._java_log_entry_match(line)
            if m:
                if entry:
                    yield info, "".join(entry).rstrip()
                    entry.clear()
                info = (
                    m.group('origin'),
                    m.group('level').strip().upper(),
                )
                entry.append(m.group('msg'))
            else:
                entry.append(line)
        if entry:
            yield info, "".join(entry).rstrip()


class _JavaLoggingStdout(_JavaLoggingBase):
    java_default = System.out
    java_setter = System.setOut


class _JavaLoggingStderr(_JavaLoggingBase):
    java_default = System.err
    java_setter = System.setErr


# noinspection PyPep8Naming
class redirect(ExitStack, ContextDecorator):
    """convenient contextdecorator for redirecting JVM output"""

    def __init__(self, stdout=True, stderr=True):
        super().__init__()
        self._stdout = stdout
        self._stderr = stderr

    def __enter__(self):
        super().__enter__()
        if self._stderr:
            self.enter_context(_JavaLoggingStderr())
        if self._stdout:
            self.enter_context(_JavaLoggingStdout())
        return self
