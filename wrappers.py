import os
import sys
import json
import shutil
import tempfile
import subprocess

def check_install(pkg, install_instructions_url):
    try:
        res = subprocess.run(['which', pkg], capture_output=True, text=True)
        if res.returncode != 0:
            raise FileNotFoundError(
                f"{pkg} not found. Please install {pkg} by following the instructions at: ",
                install_instructions_url
            )
        return res.stdout.strip()
    except Exception as e:
        print(f"An error occurred: {e}")
        raise
    

YT_DLP_BIN = check_install("yt-dlp", "https://github.com/yt-dlp/yt-dlp/wiki/Installation")
FFMPEG_BIN = check_install("ffmpeg", "https://ffmpeg.org/download.html")
DATA_ROOT = os.path.join(os.getcwd(), 'data-test')
AUDIO_OUTPUT = os.path.join(os.getcwd(), DATA_ROOT, 'audio')
TRANSCRIPTION_OUTPUT = os.path.join(os.getcwd(), DATA_ROOT, 'processed')
DEFAULT_WHISPER_MODEL_BIN = 'ggml-base.en.bin'
DEFAULT_LLAMA_MODEL_BIN = 'llama-2-7b.Q4_K_M.gguf'
DEFAULT_SUMMARIZE_FEATURES_PROMPT = """You are an experienced and savvy product designer with many years of experience as a full-stack engineer.
This is a product explainer transcript. 

%s

Summarize the content in a JSON output, highlighting the key features of the app, who is likely the target user, and include relevant implementation and user experience details.
"""


def ytdlp_extract_audio(
    url, 
    out_dir=AUDIO_OUTPUT, 
    filename=None, 
    verbosity=1
):
    
    with tempfile.TemporaryDirectory() as tmpdir:
        if verbosity >= 1:
            print("Extracting audio from {}...".format(url), end=' ')
        subprocess.run(
            [
                YT_DLP_BIN,
                url,
                "-o",
                f"{tmpdir}/%(upload_date)s_%(title)s.%(ext)s",
                "--extract-audio",
                "--audio-format", "mp3",
                "--ffmpeg-location", FFMPEG_BIN  
            ],
            stdout = subprocess.DEVNULL,
            stderr = subprocess.DEVNULL
        )
        tmp_filename_mp3 = os.listdir(tmpdir)[0]
        tmp_filename_wav = tmp_filename_mp3.replace('.mp3', '.wav')
        if verbosity >= 1:
            print("Converting .mp3 to .wav 16-bit.")
        subprocess.run(
            [
                FFMPEG_BIN,
                '-i', os.path.join(tmpdir, tmp_filename_mp3),
                '-ar', '16000',
                '-ac', '1',
                '-c:a', 'pcm_s16le',
                os.path.join(tmpdir, tmp_filename_wav)
            ],
            stdout = subprocess.DEVNULL,
            stderr = subprocess.DEVNULL
        )
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        if filename is None:
            audio_filename = os.path.join(out_dir, tmp_filename_wav)
        else:
            audio_filename = os.path.join(out_dir, tmp_filename_wav)
        shutil.move(os.path.join(tmpdir, tmp_filename_wav), audio_filename)
    return audio_filename


def transcribe(
    wav_filepath_full, 
    path_to_whisper_cpp = os.path.join(os.getcwd(), 'whisper.cpp'),
    whisper_model = DEFAULT_WHISPER_MODEL_BIN,
    out_dir = TRANSCRIPTION_OUTPUT
):
    print(f'Transcribing {wav_filepath_full}...')
    subprocess.run(
        [
            os.path.join(path_to_whisper_cpp, 'main'),
            "-m", os.path.join(path_to_whisper_cpp, 'models', whisper_model),
            "-f", wav_filepath_full,
            "--output-txt"
        ],
        stdout = subprocess.DEVNULL,
        stderr = subprocess.DEVNULL
    )
    tmp_txt_filepath_full = wav_filepath_full.replace('.wav', '.wav.txt')
    wav_file_name = wav_filepath_full.split('/')[-1]
    txt_file_name = wav_file_name.replace('.wav', '.txt')
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    out_txt_filepath_full = os.path.join(out_dir, txt_file_name)
    shutil.move(tmp_txt_filepath_full, out_txt_filepath_full)
    return out_txt_filepath_full


def summarize_key_features(
    transcript_filepath, # absolute path
    out_dir,             # absolute path
    path_to_llama_cpp = os.path.join(os.getcwd(), 'llama.cpp'),
    llama_model = DEFAULT_LLAMA_MODEL_BIN,
    prompt_template = DEFAULT_SUMMARIZE_FEATURES_PROMPT, 
    n = 2048 + 400,
    c = 2048,
    json_schema_file = None,
    write_to_out_dir = True,
    verbosity = 1
):

    # Storage that persists outside this function.
    prompt_filepath = os.path.join(out_dir, f'summary_prompt.txt')
    out_txt_filepath = os.path.join(out_dir, f'summary_generation.txt')
    out_json_filepath = os.path.join(out_dir, f'summary_generation.json')
    # TODO: put the above into SQLite DB.
    
    # Read transcript file to construct prompt. Store it for analysis.
    with open(transcript_filepath, 'r') as f:
        transcript = f.read()
    prompt = prompt_template % transcript
    with open(prompt_filepath, 'w') as f:
        f.write(prompt)

    # Start container to run command
    cmd = [
        # https://github.com/ggerganov/llama.cpp/blob/master/examples/main/README.md#common-options
        os.path.join(path_to_llama_cpp, 'main'),
        "-m", os.path.join(path_to_llama_cpp, 'models', llama_model),
        "--file", prompt_filepath,
        "-n", str(n), # number of tokens to predict
        "-c", str(c), # context size
        "-e",         # process escapes
    ]
    if json_schema_file is not None:
        # Compute the JSON grammar using a handy tool in llama.cpp.
        json_grammar_result = subprocess.run(
            [
                sys.executable, 
                os.path.join(path_to_llama_cpp, 'examples/json_schema_to_grammar.py'), 
                json_schema_file
            ], 
            capture_output=True,
            text=True
        )
        if json_grammar_result.returncode != 0:
            print(f"Error executing grammar script: {result.stderr}")
            exit(1)
        json_grammar = json_grammar_result.stdout.strip()
        cmd.extend(['--grammar', json_grammar])
    if verbosity >= 2:
        print(' '.join(cmd))
    if verbosity >= 1:
        print(f'Summarizing {transcript_filepath}...')
    with open(out_txt_filepath, "w") as file:
        subprocess.run(cmd, stdout = file)

    # Postprocess to produce JSON.
    with open(prompt_filepath, 'r') as f:
        prompt = f.read()
    with open(out_txt_filepath, 'r') as f:
        generation = f.read()
    START_TOKEN = '<s>'
    END_TOKEN = '</s>'
    generated_json_str = generation[len(prompt) + len(START_TOKEN): -len(END_TOKEN)]
    with open(out_json_filepath, 'w') as f:
        f.write(json.dumps(json.loads(generated_json_str)))
        
    return prompt_filepath, out_txt_filepath, out_json_filepath