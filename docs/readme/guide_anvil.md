# anvil Detailed Guide

GitHub operations toolkit. Auto-generate commit messages and create draft PRs.

## Skill Details

### commit

```
/anvil:commit [message]
```

| Argument  | Description                                            |
| --------- | ------------------------------------------------------ |
| `message` | Commit message (omit for auto-generation from changes) |

### create-pr

```
/anvil:create-pr [base-branch]
```

| Argument      | Description                                                                              |
| ------------- | ---------------------------------------------------------------------------------------- |
| `base-branch` | Base branch (omit to auto-detect from `.git_information.yaml` > develop > main > master) |

## Requirements

- [gh CLI](https://cli.github.com/) (authenticated)
