# Git utilities

# Imports
import os
import sys
import git
import inspect

# Get a git repository by path/object
def get_git_repo(path=None, obj=None):
	# path = Path to search for a containing git repository (takes priority over obj)
	# obj = Object that can be resolved to a path using inspect.getfile(), or None = Current working directory, str = Module name
	# Return git repository (fail => None)

	try:
		if path is not None:
			search_path = path
		elif obj is None:
			search_path = os.getcwd()
		elif isinstance(obj, str):
			search_path = inspect.getfile(sys.modules[obj])
		else:
			search_path = inspect.getfile(obj)
	except (TypeError, LookupError):
		return None

	try:
		repo = git.Repo(path=search_path, search_parent_directories=True)
	except git.exc.GitError:
		return None

	return repo

# Get the HEAD commit of a git repository
def get_repo_head(repo):
	# repo = Git repository to get the HEAD commit of
	# Return HEAD commit (fail => None)

	if repo is None:
		return None

	try:
		head_commit = repo.head.commit
	except (ValueError, git.exc.GitError):
		return None

	return head_commit

# Get the symbolic reference (if possible) corresponding to the current HEAD
def head_symbolic_ref(repo):
	# repo = Git repository to get the symbolic HEAD reference of
	# Return string symbolic reference (or commit hash if none is available)
	try:
		symref = repo.git.symbolic_ref('-q', 'HEAD', short=True)
	except git.exc.GitCommandError:
		symref = repo.git.rev_parse('HEAD')
	return symref

# Get a list of current tracked working changes
def tracked_working_changes_list(repo, unstaged=True, staged=True, binary=False):
	# repo = Git repository to get the tracked working directory changes of in the form of a list of changes
	# unstaged = Whether to include unstaged changes
	# staged = Whether to include staged changes
	# binary = Whether to include binary files (whether staged or unstaged)
	# Return a list of tuple(file_is_binary, file_git_path, file_diff), where file_git_path is the path of the file relative to the git repository root

	changes_list = []

	if repo is None or not (unstaged or staged):
		return changes_list

	diff_args = []
	diff_kwargs = {'binary': binary}
	if unstaged and staged:
		diff_args.append('HEAD')
	elif staged:
		diff_kwargs['cached'] = True

	changed_files = repo.git.diff(*diff_args, name_only=True, **diff_kwargs).splitlines()

	for file in changed_files:
		file_numstats = repo.git.diff(*diff_args, '--', file, numstat=True, **diff_kwargs)
		if not file_numstats:
			raise ValueError(f"Unexpected empty return value when attempting to query whether file is binary: {file}")
		is_binary = (file_numstats[0] == '-')
		if not binary and is_binary:
			continue
		file_diff = repo.git.diff(*diff_args, '--', file, **diff_kwargs)
		if file_diff:
			changes_list.append((is_binary, file, file_diff))

	return changes_list

# Get a diff/patch of current tracked working changes
def tracked_working_changes(repo, unstaged=True, staged=True, binary=False):
	# repo = Git repository to get the tracked working directory changes of in the form of a diff (i.e. patch)
	# unstaged = Whether to include unstaged changes in the diff
	# staged = Whether to include staged changes in the diff
	# binary = Whether to include binary files in the diff (whether staged or unstaged)
	# Return the required diff (i.e. patch) in string format
	changes_list = tracked_working_changes_list(repo, unstaged=unstaged, staged=staged, binary=binary)
	changes_list.sort()
	return '\n'.join(change[2] for change in changes_list)

# Get a list of current untracked working changes
def untracked_working_changes_list(repo, binary=False):
	# repo = Git repository to get the untracked working directory changes of in the form of a list of changes
	# binary = Whether to include binary files
	# Return a list of tuple(file_is_binary, file_git_path, file_diff), where file_git_path is the path of the file relative to the git repository root

	changes_list = []

	if repo is None:
		return changes_list

	diff_args = ['--', '/dev/null']
	diff_kwargs = {'binary': binary, 'no_index': True, 'with_exceptions': False}

	for file in repo.untracked_files:
		file_numstats = repo.git.diff(*diff_args, file, numstat=True, **diff_kwargs)
		if not file_numstats:
			raise ValueError(f"Unexpected empty return value when attempting to query whether file is binary: {file}")
		is_binary = (file_numstats[0] == '-')
		if not binary and is_binary:
			continue
		file_diff = repo.git.diff(*diff_args, file, **diff_kwargs)
		if file_diff:
			changes_list.append((is_binary, file, file_diff))

	return changes_list

# Get a diff/patch of current untracked working changes
def untracked_working_changes(repo, binary=False):
	# repo = Git repository to get the untracked working directory changes of in the form of a diff (i.e. patch)
	# binary = Whether to include binary files in the diff
	# Return the required diff (i.e. patch) in string format
	changes_list = untracked_working_changes_list(repo, binary=binary)
	changes_list.sort()
	return '\n'.join(change[2] for change in changes_list)

# Get a diff/patch of all current working changes
def all_working_changes(repo, tracked_binary=True, untracked_binary=False):
	# repo = Git repository to get all working directory changes of in the form of a diff (i.e. patch)
	# tracked_binary = Whether to include tracked binary files in the diff
	# untracked_binary = Whether to include untracked binary files in the diff
	# Return the required diff (i.e. patch) in string format
	changes_list = tracked_working_changes_list(repo, unstaged=True, staged=True, binary=tracked_binary)
	changes_list.extend(untracked_working_changes_list(repo, binary=untracked_binary))
	changes_list.sort()
	return '\n'.join(change[2] for change in changes_list)
# EOF
