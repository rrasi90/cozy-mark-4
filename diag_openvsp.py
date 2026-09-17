import openvsp
print("OpenVSP import successful.")
try:
    # Attempt to get version information if available
    print(f"OpenVSP API Version: {openvsp.__version__}")
except Exception as e:
    print(f"Could not determine OpenVSP version (This is normal if the package variable doesn't expose it): {e}")

# Test headless compatibility checks, referencing documented flags.
try:
    openvsp_config = openvsp.get_global_config()
    if hasattr(openvsp_config, 'set_flag'):
        print("Successfully accessed OpenVSP global configuration.")
        # Example setting needed for headless automation
        # We check if the flag setter exists before trying to use it
        if hasattr(openvsp_config, 'LOAD_GRAPHICS') and isinstance(getattr(openvsp_config, 'LOAD_GRAPHICS'), bool):
            print(f"Initial LOAD_GRAPHICS status: {openvsp_config.LOAD_GRAPHICS}")
except Exception as e:
    print(f"Warning during config check (Facade/Headless setup might be required): {e}")