# Modelos do MediaPipe (Google, licença Apache 2.0)

`hand_landmarker.task` e `face_landmarker.task`, copiados de
`https://storage.googleapis.com/mediapipe-models/{hand,face}_landmarker/{hand,face}_landmarker/float16/1/`.
Ficam no repositório porque a sessão de nuvem do Claude não alcança `storage.googleapis.com` (01/11/2026);
o `efeitos.py` usa `~/.tutorial-sistema/modelos/` se existir, senão esta pasta, senão baixa do endereço acima.
Os pesos do Robust Video Matting (107 MB) não cabem aqui: vêm dos releases do GitHub do projeto (alcançável).
