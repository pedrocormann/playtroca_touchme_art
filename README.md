# Playtronica TouchMe Art — Osvaldinho

Sistema para obra interativa: visitantes tocam fios de cobre que saem de pedras com circuitos. A [TouchMe da Playtronica](https://playtronica.com/products/touchme) capta o toque como MIDI, e o Raspberry Pi dispara samples de áudio através do fone/sistema de som.

## Arquitetura

```
 fio de cobre (toque humano)  →  TouchMe (USB-MIDI)  →  Raspberry Pi 4
                                                            │
                                                  ┌─────────┴──────────┐
                                                  │                    │
                                          midi_listener.py      Flask (porta 8080)
                                                  │                    │
                                                  ▼                    ▼
                                              sampler.py         config UI / API
                                          (pygame.mixer)               │
                                                  │                    │
                                                  ▼                    │
                                          jack 3.5mm fone   ◄──────────┘
                                                            config.json
```

Um único processo Python orquestra:

- **midi_listener** — escuta a TouchMe via ALSA MIDI, dispara `play_note` / `release_note`
- **sampler** — `pygame.mixer` polifônico (16 canais), com retrigger lockout, hold-to-play, fade-out e cap de duração
- **server** — Flask serve a UI em `http://<ip-do-pi>:8080`, persistindo mudanças em `config.json`

O serviço sobe automaticamente no boot via systemd. Não há display obrigatório — toda configuração é feita pela rede.

## Comportamento

- **hold-to-play** (default ligado): enquanto o visitante toca, o áudio toca em loop; ao soltar, fade-out
- **retrigger lockout**: o mesmo sample não dispara de novo se o anterior aconteceu há menos de N segundos (configurável; default 2 s)
- **fade-out ao soltar**: default 5 s
- **duração máxima por toque**: default 20 s (mesmo se o visitante segurar mais tempo)

Tudo isso é ajustável em tempo real pela UI.

## Setup inicial no Raspberry Pi

A partir de um Pi 4 com Raspberry Pi OS Bookworm, usuário `piripak`, na mesma rede Wi-Fi do Mac de desenvolvimento:

```bash
# (no Mac) gerar chave SSH e copiar pro Pi
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_playtronica
ssh-copy-id -i ~/.ssh/id_ed25519_playtronica.pub piripak@<ip-do-pi>

# (no Mac) configurar ~/.ssh/config com o alias "playtronica"
# Host playtronica
#   HostName <ip-do-pi>
#   User piripak
#   IdentityFile ~/.ssh/id_ed25519_playtronica

# (no Mac) deploy completo: rsync + install + systemd enable + restart
tools/deploy.sh
```

Após o primeiro deploy, o serviço está rodando e configurado pra subir automaticamente em todo boot do Pi.

## Adicionar / trocar samples

1. Coloca novos arquivos em `samples/sources/` (mp3, wav, ogg, m4a, flac, aac)
2. Roda `tools/deploy.sh` (sincroniza + converte para wav no Pi + restart)
3. Abre a UI no navegador (celular/laptop na mesma rede): `http://<ip-do-pi>:8080`
4. Pra cada pad da TouchMe, escolhe o sample no menu

A conversão é idempotente — só re-converte se a fonte é mais nova.

## Reconfigurar a TouchMe

Por padrão a TouchMe envia **notas MIDI** (note on/off por pad). Pra mudar pra modo CC (intensidade do toque como sinal contínuo), use o software [PlayDuo da Playtronica](https://playtronica.com) plugando a TouchMe direto em um computador. Depois reconecta no Pi. Suporte a CC mode no app está planejado para V2.

## Comandos úteis

```bash
ssh playtronica                              # SSH no Pi
ssh playtronica 'sudo journalctl -u playtronica -f'   # logs em tempo real
ssh playtronica 'sudo systemctl restart playtronica'  # restart
ssh playtronica 'amixer set Master 85%'      # ajustar volume global ALSA
```

## Stack

- Raspberry Pi 4 Model B (4 GB) · Raspberry Pi OS Bookworm
- Python 3.11 · Flask · mido · python-rtmidi · pygame.mixer
- ffmpeg (mp3 → wav) · ALSA (saída jack 3.5 mm)
- systemd para autostart
