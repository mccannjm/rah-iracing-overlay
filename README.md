# **RAH iRacing Overlay**

**iRacing Input Telemetry Overlay** is an open-source Python-based project that provides real-time telemetry from iRacing, displaying input data both through a web interface so you can put it on programs like OBS or screen overlay for using it on your game.

I just didn't wanted to pay for some overlays subcriptions to have the overlay that I actually wanted, so why not trying? I hope you feel the same, this is free of course ;)

<p align="center">
  <img src=https://github.com/RaulArcos/rah-iracing-overlay/blob/development/images/input-telemetry.gif>
  <img src=https://github.com/RaulArcos/rah-iracing-overlay/blob/development/images/interface.png  width="600">
</p>

## **Table of Contents**

- [Compilation](#compilation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## **Compilation**

You can compile your own modified version, or make use of the precompiled one you can find on releases of this repo.

### **Prerequisites**

Before compiling, make sure you have the following installed:

- **Python 3.10+**: Ensure you have Python installed. You can download it from [here](https://www.python.org/downloads/).
- **iRacing SDK**: Install iRacing for telemetry data [here](https://github.com/kutu/pyirsdk.git).
- **Requirements file**: You will find a requirements.txt file on the repo for you to get all the libraries.
  
### **1. Clone the Repository**

```bash
git clone https://github.com/RaulArcos/rah-iracing-overlay.git
cd iracing-input-telemetry-overlay
```

### **2. Install Dependencies**

**Option A: Use the automated setup script (recommended)**
```bash
python3 setup_environment.py
```
This script will:
- Detect your system's pip command (pip3, pip, or python -m pip)
- Handle virtual environments if needed (for externally-managed systems)
- Install all security-patched dependencies
- Create a convenience run script

**Option B: Simple installation (if your system allows global installs)**
```bash
python3 install_requirements.py
```

**Option C: Manual installation**
```bash
# For systems that allow global installs
pip3 install -r requirements.txt

# For systems requiring virtual environments
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### **Security Updates Included**
This version includes critical security fixes:
- **Flask 3.1.2** (patches CVE-2024-34069, CVE-2024-56326, and others)
- **Eventlet 0.40.3** (patches CVE-2025-58068 HTTP Request Smuggling)
- **Input validation** with Marshmallow schemas
- **CORS restrictions** to specific origins
- **Path traversal protection** for file serving
- **Security headers** implementation

### **3. Compile into an EXE file**

```bash
python3.10.exe (or your version) build_exe.py
```

## **Usage**

Just open the .exe file like a normal windows program, you will be welcomed by an easy interace to open any of the overlays, as well as modify its position or opening it on their web version to get the link for OBS.

<p align="center">
  <img src=https://github.com/RaulArcos/rah-iracing-overlay/blob/development/images/interface_with_movement.png  width="600">
</p>

## Windows Security: Unblocking DLL Files

If you encounter errors related to `Python.Runtime.dll` or other DLL files failing to load, it might be due to Windows blocking these files after being downloaded from another computer.
It is always better to build your own version, but if you don't know or simply don't want to, you will have to do this.

### Steps to Unblock DLLs:
1. Navigate to the `.dll` files, e.g.:
   - `\RAH_Telemetry_Overlay_0.2.1_internal\pythonnet\runtime\Python.Runtime.dll`
   - all `.dll` files in `\RAH_Telemetry_Overlay_0.2.1_internal\webview\lib\`

2. Right-click each `.dll` file and select **Properties**.

3. In the **General** tab, check the **"Unblock"** checkbox at the bottom (if it’s visible).

4. Click **OK**.

This is needed because Windows may block DLL files that come from another computer, causing the program to fail to load them properly.

## **Contributing**

I hope you want to take part on this journey! Everyone is welcome to add diferent overlays to show interesting data like stadings positions, predicted points... you name it! These are the steps you should do to make this posible:

Remember!! You will find another README file on /src/overlays with steps to implement new overlays as easy as posible!

1. Fork the project.
2. Clone your forked repository to your local machine.
3. Create a new branch for your feature or fix:
 ```bash
git checkout -b feature-name
```
4. Commit your changes
```bash
git commit -m "Add some feature"
```
5. Pust your changes!
```bash
git push origin feature-name
```

## **License**
This project is licensed under the MIT License.
