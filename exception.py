import logging
from errno import errorcode

class NotSupportedError(Exception):
    def __init__(self, *args, **kwargs):
        super(NotSupportedError, self).__init__(*args, **kwargs)


class ExternalCommandError(Exception):
    def __init__(self, err, cmd=None, argdict=None, code=None):
        self.code = abs(code) if code is not None else None
        code_string = errorcode.get(self.code, str(self.code))
        argdict = argdict if isinstance(argdict, dict) else {}
        if cmd is None and self.code is None:
            s = err
        elif cmd is None:
            s = 'error={} code={}'.format(err, code_string)
        else:
            cmd = cmd['prefix'] if isinstance(cmd, dict) and 'prefix' in cmd else cmd
            s = 'Executing "{} {}" failed: "{}" code={}'.format(cmd, ' '.join(
                ['{}={}'.format(k, v) for k, v in argdict.items()]), err, code_string)
        super(ExternalCommandError, self).__init__(s)

