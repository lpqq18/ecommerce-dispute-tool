module.exports = {
  apps: [
    {
      name: "ecommerce-dispute-tool",
      cwd: "/var/www/ecommerce-dispute-tool",
      script: "server.py",
      interpreter: "/var/www/ecommerce-dispute-tool/.venv/bin/python",
      env: {
        HOST: "127.0.0.1",
        PORT: "4173",
        CASE_STORE_DRIVER: "json",
        CASE_DATA_DIR: "/var/www/ecommerce-dispute-tool/data",
        ADMIN_TOKEN: "change-this-admin-token",
        OCR_PROVIDER: "auto",
        OCR_REQUIRE_REAL: "0",
        OPENAI_MODEL: "gpt-4o-mini",
        OBSERVABILITY_ENABLED: "1",
      },
    },
  ],
};
