import sys
import os

OPENVSP_ROOT = r"C:\OpenVSP-3.51.2-win64"
# Add the top-level python directory and bin/scripts to sys path, 
# addressing potential DLL load points for OpenVSP's C++ components.
sys.path.append(os.path.join(OPENVSP_ROOT, 'python'))
sys.path.append(os.path.join(OPENVSP_ROOT, 'scripts'))

print("--- Attempting to import openvsp with path adjustments ---")
try:
    import openvsp
    print("\n[SUCCESS] openvsp module imported successfully!")
    print(f"OpenVSP library details:")
    # Forcing a minimal feature check that relies on the API being loaded
    config = openvsp.get_global_config()
    load_graphics = config.LOAD_GRAPHICS
    print(f"  - LOAD_GRAPHICS Status: {openvsp.__version__ if hasattr(openvsp, '__version__') else 'N/A'}")

except ModuleNotFoundError as e:
    print(f"\n[FAILURE] openvsp module could not be found even after path manipulation. Error: {e}")
except AttributeError as e:
     # Catches errors if methods like get_global_config() don't exist in loaded version
    print(f"\n[PARTIAL FAILURE] OpenVSP imported, but API method check failed. The environment might be working, but the function signature is wrong. Details: {e}")

print("\n--- Diagnostic Test Complete ---")