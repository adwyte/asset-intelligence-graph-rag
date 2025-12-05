import React, { useEffect, useRef, useState } from "react";
import { uploadAudioAndTranscribe } from "../api";

interface AudioRecorderProps {
  onTranscription: (text: string) => void;
}

const AudioRecorder: React.FC<AudioRecorderProps> = ({ onTranscription }) => {
  const [recording, setRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const startRecording = async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert("Audio recording not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      chunksRef.current = [];

      mr.ondataavailable = (e: BlobEvent) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        chunksRef.current = [];
        setLoading(true);
        try {
          const text = await uploadAudioAndTranscribe(blob);
          if (text) onTranscription(text);
        } catch (e) {
          console.error("STT failed:", e);
          alert("Transcription failed.");
        } finally {
          setLoading(false);
        }
      };

      mr.start();
      setRecording(true);
    } catch (e) {
      console.error("Could not start recording:", e);
      alert("Could not access microphone.");
    }
  };

  const stopRecording = () => {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== "inactive") {
      mr.stop();
      setRecording(false);
    }
  };

  const handleClick = () => {
    if (recording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      style={{
        padding: "8px 16px",
        borderRadius: 999,
        border: "1px solid #d4d4d8",
        background: recording ? "#fee2e2" : "#ffffff",
        cursor: "pointer",
        fontSize: 14,
      }}
    >
      {loading
        ? "Transcribing..."
        : recording
        ? "● Stop recording"
        : "🎤 Speak"}
    </button>
  );
};

export default AudioRecorder;
