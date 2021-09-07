// Camera Sync - TTL triggering with Teensy board
// Inter-frame interval precision: ~ +/- 1.5 us
// Inter-frame interval accuracy: ~ +40 ns
// Synchronicity: ~ ? ns (not tested yet)

// User-set parameters
uint32_t baudrate = 115200;
uint32_t time_scale = 1e6; // 1e3 for micros; 1e6 for micros

// Global variables
int DIG_out_pins[100];
int n_sync;
float frame_rate_in = 0;
float frame_rate_out = 0;
unsigned long frame_start, frame_period;


void setup( void ) {

  Serial.begin(baudrate);
  delay(500);
  Serial.print("Set baudrate to ");
  Serial.print(baudrate);

  // Set DigPins using Python or Serial Monitor input
  n_sync = SetDigPins();

  // Set Frame Rate using Python or Serial Monitor input
  frame_rate_out = SetFrameRate();
  frame_period = SetFramePeriod(frame_rate_out);

  // Wait for streams and cams to initialize
  ResetTimer(); 
}


int SetDigPins() {
  Serial.println("");
  Serial.print("Enter string, separated by commas: # dig pins, dig pins, frame rate:");

  // Receive Dig Pin array size from Python or Serial Monitor
  while (Serial.available() == 0) {}
  int num_pins = int( (unsigned int) Serial.parseFloat());

  // Print result and initialize array
  Serial.print(num_pins);
  
  for ( int i = 0; i < num_pins; i++ ) {
    Serial.println("");
    Serial.print("Enter next digital pin as int: ");

    // Receive digital pin
    while (Serial.available() == 0) {}
    int input = int( (unsigned int) Serial.parseFloat());
    Serial.print(input);

    // Append pin number to array
    DIG_out_pins[i] = input;
  }

  for ( int i = 0; i < num_pins; i++ ) {
    pinMode(DIG_out_pins[i], OUTPUT);
    digitalWrite(DIG_out_pins[i], LOW);
  }

  return num_pins;
}


unsigned long SetFrameRate() {
  Serial.println("");
  Serial.print("Enter your frame rate: ");

  // Wait to receive frame rate from Python or Serial Monitor...
  while (Serial.available() == 0) {}
  frame_rate_in = Serial.parseFloat();

  // Output frame rate, avoid negative values
  if (frame_rate_in == 0) {}
  else if (frame_rate_in < 0) {
    frame_rate_out = 0;
  }
  else {
    frame_rate_out = frame_rate_in;
  }

  // Print results
  Serial.println("");
  Serial.print("Frame rate set to: ");
  Serial.print(frame_rate_out);
  Serial.print(" fps.");

  return frame_rate_out;
}


unsigned long SetFramePeriod( unsigned long fr ) {
  // Calculate frame period and pulse duration
  // Avoid divide-by-zero error
  if (fr == 0) {
    frame_period = 0xFFFFFFFF;
  }
  else {
    frame_period = time_scale / fr;
  }

  Serial.println("");
  Serial.print("Frame period set to: ");
  Serial.print(frame_period);
  Serial.print(" microseconds.");

  return frame_period;
}


void FlushSerialBuffer() {
  while (Serial.available() != 0) {
    Serial.parseFloat();
  }
}


void ResetTimer() {
  delay(4000);
  FlushSerialBuffer();
//  frame_count = 0;
  frame_start = micros();
}


void SetPinsHigh() {
  // Disable interrupts to synchronize TTLs
  noInterrupts();
  for ( int i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], HIGH);
  }
  interrupts();
}


void SetPinsLow() {
  // Disable interrupts to synchronize TTLs
  noInterrupts();
  for ( int i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], LOW);
  }
  interrupts();
}


void loop( void ) {
  if (Serial.available())
  {
    SetPinsLow();
    n_sync = SetDigPins();
    frame_rate_out = SetFrameRate();
    frame_period = SetFramePeriod(frame_rate_out);
    ResetTimer();
  }

  if (frame_rate_out > 0) {
    SetPinsLow();

    // Wait until end of this pulse period
    while (micros() - frame_start < frame_period / 2) {}

    SetPinsHigh();

    // Wait until end of this frame period
    while (micros() - frame_start < frame_period) {}

    frame_start = frame_start + frame_period;
  }
}
