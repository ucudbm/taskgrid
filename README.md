# taskgrid
TaskGrid is a distributed task execution system. A task is a script (bash/python/powershell) that runs tests and completes work. Tasks are distributed by the Grid Scheduler (GS) to Grid Executors (GE). Each GE picks up a task, executes it, and reports results back to the GS. Grid Packages (GP) handle storage.
