#!/usr/bin/env bash
set -euo pipefail

# Encapsular la ejecución en main() permite usar return al ser cargado con 'source' por docker-entrypoint.sh.
main() {
    local seed_conf_path="${SEED_CONF_PATH:-/docker-entrypoint-initdb.d/seed.conf}"
    local cache_dir="${ARCHIVE_CACHE_DIR:-/datasets-cache}"
    local archive_file=""
    local archive_gzip=""
    local datasets_raw=""
    local raw_line=""
    local cleaned_line=""
    local key=""
    local value=""
    local item=""
    local magic_hex=""
    local -a selected_datasets=()
    local -a ns_args=()
    local -a auth_args=()
    local -a gzip_args=()

    if [[ ! -f "${seed_conf_path}" ]]; then
        echo "[init-db] Info: '${seed_conf_path}' not found. Booting empty MongoDB instance without sample data."
        return 0
    fi

    # Leer clave=valor manualmente sin usar 'source' ni 'eval' protege contra ejecución arbitraria desde seed.conf.
    while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
        cleaned_line="${raw_line%$'\r'}"
        cleaned_line="${cleaned_line#"${cleaned_line%%[![:space:]]*}"}"
        cleaned_line="${cleaned_line%"${cleaned_line##*[![:space:]]}"}"

        if [[ -z "${cleaned_line}" || "${cleaned_line}" == \#* ]]; then
            continue
        fi

        if [[ "${cleaned_line}" == *=* ]]; then
            key="${cleaned_line%%=*}"
            value="${cleaned_line#*=}"
            key="${key%"${key##*[![:space:]]}"}"
            value="${value#"${value%%[![:space:]]*}"}"

            case "${key}" in
                ARCHIVE_FILE)
                    archive_file="${value}"
                    ;;
                ARCHIVE_GZIP)
                    archive_gzip="${value}"
                    ;;
                DATASETS)
                    datasets_raw="${value}"
                    ;;
                *)
                    echo "[init-db] Warning: Ignoring unknown key '${key}' in '${seed_conf_path}'."
                    ;;
            esac
        else
            # Soportar líneas simples heredadas mejora resiliencia ante edición manual del estudiante.
            if [[ -n "${datasets_raw}" ]]; then
                datasets_raw="${datasets_raw},${cleaned_line}"
            else
                datasets_raw="${cleaned_line}"
            fi
        fi
    done < "${seed_conf_path}"

    if [[ -z "${datasets_raw}" ]]; then
        echo "[init-db] Info: '${seed_conf_path}' declares no datasets. Booting empty MongoDB instance."
        return 0
    fi

    archive_file="${archive_file:-sampledata.archive}"
    # Restringir ARCHIVE_FILE a un nombre base válido impide path traversal fuera de /datasets-cache.
    if [[ ! "${archive_file}" =~ ^[a-zA-Z0-9._-]+$ || "${archive_file}" == *".."* ]]; then
        echo "[init-db] Error: Invalid ARCHIVE_FILE '${archive_file}' in '${seed_conf_path}'." >&2
        return 1
    fi

    local archive_path="${cache_dir%/}/${archive_file}"
    if [[ ! -s "${archive_path}" ]]; then
        echo "[init-db] Error: Archive '${archive_path}' is missing or empty." >&2
        echo "[init-db] Run 'docker compose run --rm configurator' before starting MongoDB." >&2
        return 1
    fi

    IFS=',' read -r -a raw_tokens <<< "${datasets_raw}"
    for item in "${raw_tokens[@]}"; do
        item="${item#"${item%%[![:space:]]*}"}"
        item="${item%"${item##*[![:space:]]}"}"
        if [[ -z "${item}" ]]; then
            continue
        fi

        # Validar identificador de base de datos evita inyección de argumentos en mongorestore.
        if [[ ! "${item}" =~ ^[a-zA-Z0-9_-]+$ ]]; then
            echo "[init-db] Error: Invalid dataset name '${item}' in '${seed_conf_path}'." >&2
            return 1
        fi

        selected_datasets+=("${item}")
        ns_args+=("--nsInclude=${item}.*")
    done

    if [[ "${#selected_datasets[@]}" -eq 0 ]]; then
        echo "[init-db] Info: No valid datasets listed in '${seed_conf_path}'. Booting empty MongoDB instance."
        return 0
    fi

    if [[ -n "${archive_gzip}" ]]; then
        case "${archive_gzip}" in
            true|TRUE|1|yes)
                gzip_args=(--gzip)
                ;;
            false|FALSE|0|no)
                gzip_args=()
                ;;
            *)
                echo "[init-db] Error: Invalid ARCHIVE_GZIP value '${archive_gzip}' (expected true or false)." >&2
                return 1
                ;;
        esac
    else
        # Detectar bytes mágicos gzip (1f8b) permite soportar contratos editados sin especificar ARCHIVE_GZIP.
        magic_hex="$(od -An -tx1 -N2 "${archive_path}" 2>/dev/null | tr -d '[:space:]')"
        if [[ "${magic_hex}" == "1f8b" ]]; then
            gzip_args=(--gzip)
        fi
    fi

    if [[ -n "${MONGO_INITDB_ROOT_USERNAME:-}" && -n "${MONGO_INITDB_ROOT_PASSWORD:-}" ]]; then
        auth_args=(
            -u "${MONGO_INITDB_ROOT_USERNAME}"
            -p "${MONGO_INITDB_ROOT_PASSWORD}"
            --authenticationDatabase admin
        )
    fi

    echo "[init-db] Restoring datasets from '${archive_path}' (gzip=${#gzip_args[@]}): ${selected_datasets[*]}"

    # Usar --host 127.0.0.1 coincide con el enlace temporal que docker-entrypoint.sh levanta en el primer arranque.
    mongorestore \
        --host 127.0.0.1 \
        --port 27017 \
        "${auth_args[@]}" \
        --archive="${archive_path}" \
        "${gzip_args[@]}" \
        --drop \
        "${ns_args[@]}"

    echo "[init-db] Sample dataset restore completed successfully."
}

main "$@"
