using System;
using System.IO;
using System.Net.Sockets;
using System.Text;

// Serial-like byte transport for the existing bounded bench receiver.
public sealed class CodexBenchTcpPort : IDisposable {
    public string Host;
    public int PortNumber = 4089;
    private TcpClient client;
    private NetworkStream stream;
    public bool IsOpen { get { return client != null && stream != null; } }
    public void Open() {
        if (IsOpen) throw new InvalidOperationException("Already open");
        client = new TcpClient();
        try {
            var connect = client.ConnectAsync(Host, PortNumber);
            if (!connect.Wait(3000)) throw new TimeoutException("TCP connect timed out");
            connect.GetAwaiter().GetResult();
            client.NoDelay = true;
            client.ReceiveBufferSize = 65536;
            stream = client.GetStream();
            stream.ReadTimeout = 500;
            stream.WriteTimeout = 2000;
        } catch { Close(); throw; }
    }
    public string ReadExisting() {
        if (!IsOpen) throw new InvalidOperationException("Closed");
        int pending = client.Available;
        if (pending == 0) {
            if (client.Client.Poll(0, SelectMode.SelectRead) && client.Available == 0)
                throw new EndOfStreamException("TCP peer closed");
            return "";
        }
        byte[] bytes = new byte[Math.Min(65536, pending)];
        return Encoding.ASCII.GetString(bytes, 0, Read(bytes, 0, bytes.Length));
    }
    public int Read(byte[] bytes, int offset, int count) {
        try {
            int read = stream.Read(bytes, offset, count);
            if (read == 0) throw new EndOfStreamException("TCP peer closed");
            return read;
        } catch (IOException ex) {
            var socket = ex.InnerException as SocketException;
            if (socket != null && (socket.SocketErrorCode == SocketError.TimedOut ||
                socket.SocketErrorCode == SocketError.WouldBlock))
                throw new TimeoutException("TCP read timed out", ex);
            throw;
        }
    }
    public int ReadByte() {
        byte[] byteValue = new byte[1];
        Read(byteValue, 0, 1);
        return byteValue[0];
    }
    public void Write(string command) {
        byte[] bytes = Encoding.ASCII.GetBytes(command);
        stream.Write(bytes, 0, bytes.Length);
    }
    public void Close() {
        if (stream != null) { stream.Dispose(); stream = null; }
        if (client != null) { client.Close(); client = null; }
    }
    public void Dispose() { Close(); }
}
