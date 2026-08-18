# Set Up Shared Add-ins Folder

[Back to README](../README.md)

## Overview

**Set Up Shared Add-ins Folder** prepares the hub folder that [Team Add-ins](./Team%20Add-ins.md) reads from. There is nothing to browse for and nothing to save: the location is a fixed convention,

```
<active hub> / Assets / Shared Addins /
```

the same shape Power Tools already uses for `Assets / Pn-Cache`. The command finds that folder or offers to create it, then reports what it found.

Because the location is a convention rather than a setting, nothing is written to disk and there is no per-machine configuration to keep in step. Every teammate on the hub reads the same folder automatically.

---

## When to run it

- The **first time** anyone on the hub sets up Team Add-ins.
- When you **join a new hub** that has no Shared Addins folder yet.
- Any time you want to **confirm** the folder is reachable and see how many packages are in it.

Running it repeatedly is harmless. If the folder already exists the command reports it and changes nothing.

---

## Prerequisites

An **Assets** project must already exist in the hub, readable by everyone who needs the add-ins.

Power Tools will not create that project: creating a project requires Fusion Team admin rights, so it is deliberately left to an administrator. The folder inside it is created on request.

> Read access to the project is all a teammate needs. Only whoever shares add-ins needs write access.

---

## How to run it

1. **Open PowerTools Preferences.** Quick Access Toolbar → **File** menu → **PowerTools Preferences**.

2. **Go to the Team Add-ins section.** The status card shows the current state:

   | State | Meaning |
   | ----- | ------- |
   | **Ready** | The folder exists; the card lists how many packages are in it |
   | **Not created** | The Assets project is there but the folder is not |
   | **No hub** | You are not signed in to a Fusion Team hub |
   | **Unavailable** | The hub could not be read; the card explains why |

3. **Click the button.** It reads *Create shared folder…* when the folder is missing and *Check folder…* when it already exists.

4. **Confirm.** When the folder has to be created, the command asks first and names the project it will create it in. When it already exists, it just reports the hub, project, folder and package count.

The result takes effect immediately — no Fusion restart. Use **Tools → Power Tools → Team Add-ins** to check the folder right away.

---

## Adopting an existing folder

Teams often create this folder by hand before installing Power Tools. The lookup matches loosely, so an existing folder is adopted rather than duplicated:

| Existing folder name | Adopted |
| -------------------- | ------- |
| `Shared Addins` | yes (exact match always wins) |
| `Shared AddIns` | yes |
| `shared add-ins` | yes |
| `SharedAddins` | yes |
| `Shared Data` | no — unrelated folder |

Only when nothing matches does the command offer to create `Shared Addins`.

---

## Troubleshooting

**"This hub has no Assets project."** Ask your Fusion Team administrator to create one. Creating a project needs admin rights, which is why this is not automated.

**"Could not create Shared Addins… Check your permissions."** You have read access to the Assets project but not write access. Ask someone with write access to run the command once; after that everyone else only needs to read.

**"Sign in to a Fusion Team hub."** Team Add-ins is a hub feature — a personal hub has no shared project to read from.

**The Team Add-ins commands are disabled.** Enable the Team Add-ins group in PowerTools Preferences → Commands and restart Fusion.

---

[Team Add-ins guide](./Team%20Add-ins.md) · [Back to README](../README.md)
