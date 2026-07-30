fn main() {
    // This function call tells cargo to pass the correct linker arguments
    // to link against the Python interpreter library.
    pyo3_build_config::use_pyo3_cfgs();
}