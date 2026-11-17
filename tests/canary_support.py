"""Disposable source-only owner CLI harness; never touches the operator home."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OWNER_REVISION = 'd57009cb004d404adf9daa5a374a1c2b37b8288e'

def owner_source():
    path = Path(os.environ.get('DOC_WARDEN_OWNER_SOURCE', ROOT / '.ci-owner-dev')).resolve()
    assert path.is_dir(), 'Set DOC_WARDEN_OWNER_SOURCE to the immutable public owner checkout'
    def git(*args):
        return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()
    assert git('rev-parse', 'HEAD') == OWNER_REVISION, 'wrong owner engine revision'
    assert git('remote', 'get-url', 'origin') in ('https://github.com/KleinPerkins/dev.git', 'git@github.com:KleinPerkins/dev.git'), 'wrong public owner origin'
    assert not git('status', '--porcelain', '--untracked-files=normal'), 'owner engine checkout must stay clean'
    return path

def snapshot(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file() and '.git' not in p.relative_to(path).parts}

@contextmanager
def fixture(kind='current'):
    with tempfile.TemporaryDirectory(prefix='canary-ci-') as temporary:
        top = Path(temporary); repo = top / 'repo'; home = top / 'home'
        repo.mkdir(); home.mkdir()
        owner = owner_source()
        if kind == 'current':
            for name in ('.planning', '_ops', 'docs', 'AGENTS.md', 'README.md'):
                source=ROOT/name;target=repo/name
                if source.is_dir():shutil.copytree(source,target)
                else:shutil.copy2(source,target)
        else:
            shutil.copytree(owner/'_ops/doc-warden/fixtures'/kind, repo, dirs_exist_ok=True)
        # No inherited hooks, credentials, shell startup files, or home configuration.
        env = {k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','TMPDIR','LANG','LC_ALL')}
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home/'config'), XDG_CACHE_HOME=str(home/'cache'),
                   GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
                   PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['git','-c','core.hooksPath=/dev/null','init','-q',str(repo)],env=env,check=True)
        subprocess.run(['git','-C',str(repo),'add','.'],env=env,check=True)
        subprocess.run(['git','-C',str(repo),'-c','core.hooksPath=/dev/null','-c','user.name=Canary fixture',
                        '-c','user.email=fixture@example.invalid','commit','-qm','Disposable source fixture'],env=env,check=True)
        def command(*args):
            return subprocess.run(['bash',str(owner/'_ops/bin/doc-warden.sh'),*args],cwd=top,env=env,
                                  text=True,capture_output=True,timeout=60)
        try:
            yield repo, command
        finally:
            assert snapshot(home) == {}, "owner command wrote to disposable home"
