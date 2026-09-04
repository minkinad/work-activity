from monitoring import Settings, create_app


def main() -> None:
    settings = Settings.from_env()
    app = create_app(settings)
    app.run(
        host=settings.api_host,
        port=settings.api_port,
        debug=False,
        ssl_context=settings.tls_context(),
    )


if __name__ == "__main__":
    main()
