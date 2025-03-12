import pkg_resources
import re
import os

# Path to your requirements.txt file
requirements_file = os.path.join(os.getcwd() , "requirements" , "req.txt")

# Read and parse requirements.txt, ignoring comments and empty lines
with open(requirements_file, "r") as f:
    reqs = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Extract module names (remove version specifiers like ==, >=, etc.)
module_names = [re.split("[<>=]", req)[0].strip() for req in reqs]

# Get installed versions
installed = {pkg.key: pkg.version for pkg in pkg_resources.working_set}

# Display versions for modules in requirements.txt
for module in module_names:
    module_key = module.lower()  # pkg_resources uses lowercase keys
    if module_key in installed:
        print(f"{module}=={installed[module_key]}")
    else:
        print(f"{module} is not installed")